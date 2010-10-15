#! /usr/bin/python

import numpy as np, math
from threading import RLock

import roslib; roslib.load_manifest('hrl_pr2_lib')
import rospy

from hrl_lib.rutils import GenericListener, ros_to_dict
from hrl_lib.data_process import signal_smooth, signal_variance

from pr2_msgs.msg import AccelerometerState

import threading

import time, string, copy

node_name = "arm_perception_monitor" 

def log(str):
    rospy.loginfo(node_name + ": " + str)

##
# Processes the AccelerometerState message, returning an average of the
# sample values and the timestamp in nanoseconds
#
# @param msg AccelometerState message
# @return (t, (x, y, z))
def accel_state_processor(msg):
    accel_msg = ros_to_dict(msg)
    x, y, z = 0., 0., 0.
    if msg.samples is None or len(msg.samples) == 0:
        return None
    for samp in msg.samples:
        x += samp.x
        y += samp.y
        z += samp.z
    x /= len(msg.samples)
    y /= len(msg.samples)
    z /= len(msg.samples)
    return (msg.header.stamp.to_nsec(), (x, y, z))

##
# Periodically logs the output of a callback function by calling it at a certain
# rate and gathering up the results into a list
class PeriodicLogger():
    ##
    # initializes the monitor but doesn't start it
    #
    # @param callback the function to be called each time
    # @param rate the rate in seconds at which to call the callback
    # @param args the function arguments to pass into the callback
    def __init__(self, callback, rate=0.01, args=None):
        self.ret = []
        self.cb = callback
        self.rate = rate
        self.args = args
        self.is_running = False
        self.num_calls = None

    ##
    # begins the monitor
    # @param num_calls the maximum number of times to call the callback
    def start(self, num_calls=None):
        if self.is_running:
            return
        self.num_calls = num_calls
        self.is_running = True
            
        self._run()

    def _run(self):
        print "_run"
        if not self.is_running:
            return
        if self.args is None:
            retval = self.cb()
        else:
            retval = self.cb(*self.args)
        print self.rate
        self.ret += [retval]

        # break if we have called the sufficent number of times
        if self.num_calls is not None:
            self.num_calls -= 1
            if self.num_calls == 0:
                self.is_running = False
                return
        self.t = threading.Timer(self.rate, self._run)
        print "end _run"

    ##
    # stops the monitor
    # @return the result of the monitor
    def stop(self):
        print "stop"
        if not self.is_running:
            return None
        self.is_running = False
        return self.ret

    ##
    # If num_calls sets to automatically terminate, return the ret vals
    def get_ret_vals(self):
        if self.is_running:
            return None
        return self.ret

##
# Periodically monitors the output of a callback function by calling it at a certain
# rate and compares it with a provided model to insure the value doesn't vary greatly
# within a degree of tolerance provided by the variance function
class PeriodicMonitor():
    ##
    # initializes the monitor but doesn't start it
    #
    # @param callback the function to be called each time
    # @param rate the rate in seconds at which to call the callback
    # @param args the function arguments to pass into the callback
    def __init__(self, callback, rate=0.01, args=None):
        self.ret = []
        self.cb = callback
        self.rate = rate
        self.args = args
        self.is_running = False
        self.mean_model = None
        self.variance_model = None
        self.std_devs = 0.
        self.failure = False

    ##
    # begins the monitor
    # TODO DOCS
    # @param num_calls the maximum number of times to call the callback
    def start(self, mean_model, variance_model, std_devs=2.5, num_calls=None, 
                                                contingency=None, contingency_args=None):
        if len(mean_model) != len(variance_model):
            log("Models must be of same length")
            return
        if self.is_running:
            return
        self.is_running = True
        self.mean_model = mean_model
        self.variance_model = variance_model
        self.std_devs = std_devs
        self.num_calls = num_calls
        self.contingency = contingency
        self.contincency_args = contingency_args
        self.model_index = 0
        self.failure = False
            
        self._run()

    def _run(self):
        if not self.is_running:
            return
        if self.args is None:
            retval = self.cb()
        else:
            retval = self.cb(*self.args)

        # go through each coordinate in the vector
        for coord_i in len(retval[1]):
            diff = abs(retval[1][coord_i] - self.mean_model[self.model_index][coord_i])
            deviation = np.sqrt(self.variance_model[self.model_index][coord_i])
            if diff > self.std_devs * deviation:
                # signal is outside allowable range
                self.failure = True
                self.is_running = False
                # call contingency function
                if contingency_args is None:
                    self.contingency()
                else:
                    self.contingency(*contingency_args)
                return
        self.ret += [retval]
        self.model_index += 1
        if self.model_index == len(self.mean_model):
            self.is_running = False
            return

        # break if we have called the sufficent number of times
        if not self.num_calls is None:
            self.num_calls -= 1
            if self.num_calls == 0:
                self.is_running = False
                return
        t = threading.Timer(self.rate, self._run)

    ##
    # stops the monitor
    # @return the result of the monitor
    def stop(self):
        if not self.is_running:
            return None
        self.is_running = False
        return self.ret

    ##
    # If num_calls sets to automatically terminate, return the ret vals
    def get_ret_vals(self):
        if self.is_running:
            return None
        return self.ret

    # TODO DOCS
    def has_failed():
        return self.failure

    # TODO DOCS
    def wait_for_completion(rate=0.01):
        while(self.is_running):
            rospy.sleep(rate)
        return not self.failure
        

##
# Monitors perception channels on the robot arms.
#
# Usecase:
# apm = ArmPerceptionMonitor(0)
# for trajectory in trajectories:
#     apm.start_training()
#     trajectory.run()
#     trajectory.wait_for_completion()
#     apm.stop_training()
# mean_function, variance_function = apm.generate_model(...)
# 
class ArmPerceptionMonitor( ):

    ##
    # Initializes the listeners on the perception topics
    #
    # @param arm 0 if right, 1 if left
    # @param rate the rate at which the perception should capture states
    def __init__(self, arm, rate=0.01):
        log("Initializing arm perception listeners")

        self.rate = rate

        if arm == 0:
            armc = "r"
        else:
            armc = "l"
        self.accel_listener = GenericListener("accel_mon_node", AccelerometerState, 
                                 "accelerometer/" + armc + "_gripper_motor",
                                 0.1, accel_state_processor)
        # all callbacks should return data in this format:
        # (t (x1, x2, ...))
        # t is time in nanoseconds
        self.perceptions = { "accelerometer" : self.accel_listener.read }
        # TODO add callbacks for tactile sensors and joint torques

        
        self.pmonitors = {}
        self.datasets = {}
        for k in self.perceptions:
            self.pmonitors[k] = None
            self.datasets[k] = None

        self.active = False
        self.cur_means_model = None
        self.cur_variance_model = None
        
        log("Finished initialization")

    ##
    # Begin capturing peception data for all of the listeners
    #
    # @param duration If None, continue capturing until stop is called.
    #                 Else, stop capturing after duration seconds have passed.
    def start_training(self, duration=None):
        if self.active:
            log("Perception already active.")
            return
        self.active = True

        for k in self.perceptions:
            self.pmonitors[k] = PeriodicLogger(self.perceptions[k], self.rate)
            self.datasets[k] = None

        for k in self.perceptions:
            if duration is None:
                self.pmonitors[k].start()
            else:
                self.pmonitors[k].start(int(duration / self.rate) + 1)

        if not duration is None:
            threading.Timer(self._wait_stop_training, duration)

    ##
    # Stop capturing perception data.  Store output data in datasets list for
    # later statistics.
    def stop_training(self):
        if not self.active:
            log("Nothing to stop.")
            return

        for k in self.perceptions:
            if self.datasets[k] is None:
                self.datasets[k] = [self.pmonitors[k].stop()]
            else:
                self.datasets[k] += [self.pmonitors[k].stop()]
        self.active = False
    
    ##
    # Blocking stop.
    def _wait_stop_training(self):
        if not self.active:
            log("Nothing to stop.")
            return

        for k in self.perceptions:
            dataset = None
            while dataset is None:
                dataset = self.pmonitors[k].get_ret_vals()

            if self.datasets[k] is None:
                self.datasets[k] = [dataset]
            else:
                self.datasets[k] += [dataset]
        self.active = False
    
    ##
    # Returns a model function of the perception over several
    # identical trajectories. 
    # 
    # @param perception the particular dataset to generate the model for
    # @param smooth_wind the window size of the smoothing function
    # @param var_wind window size of the variance function
    # @param var_smooth_wind window size of the smoothing function on the variance
    # @return mean function, variance function
    def generate_model(self, perception, smooth_wind=None, var_wind=None, 
                                         var_smooth_wind=None):

        model_list = self.datasets[perception]
        import pdb; pdb.set_trace()
        
        if model_list is None:
            log("No data to generate model for")
            return None

        if self.active:
            log("Perception already active.")
            return None

        # get the minimum model length
        lens = [len(m) for m in model_list]
        min_len = np.min(lens)

        if min_len <= 10:
            log("Too few datapoints for good model, min_len=" % (min_len))
            return None

        # dynamic finding of parameters
        if smooth_wind is None:
            smooth_wind = min(max(10, int(min_len * 0.05)), 100)
        if var_wind is None:
            var_wind = min(max(10, int(min_len * 0.05)), 50)
        if var_smooth_wind is None:
            var_smooth_wind = min(max(10, int(min_len * 0.05)), 100)


        ret_means, ret_vars = [], []
        # find the number of coordinates from the first element
        num_coords = len(model_list[0][0][1])
        for coord in range(num_coords):
            mean_models, variance_models = [], []
            for model in model_list:
                # extract only the data stream for a single coordinate (all x values)
                model_coord = zip(*zip(*model)[1])[coord]
                cur_mean_model = signal_smooth(np.array(model_coord), smooth_wind)
                mean_models += [cur_mean_model]
                sig_var = signal_variance(model_coord, cur_mean_model, var_wind)
                variance_models += [signal_smooth(np.array(sig_var), var_smooth_wind)]
            
            num_models = len(mean_models)
            avg_means_model, avg_vars_model = [], []
            # find the average case over the several runs
            for k in range(min_len):

                # this finds the average mean and variance across all trials
                sum_mean, sum_var = 0., 0.
                for j in range(num_models):
                    sum_mean += mean_models[j][k]
                    sum_var += variance_models[j][k]
                avg_mean = sum_mean / num_models
                avg_var = sum_var / num_models

                # this finds the variance across different trials
                sum_model_var = 0.
                for j in range(num_models):
                    sum_model_var += (mean_models[j][k] - avg_mean) ** 2
                # since the noise variance and the model variance are independent,
                # we sum them together
                total_model_var = sum_model_var / num_models + avg_var

                avg_means_model += [avg_mean]
                avg_vars_model += [total_model_var]
            ret_means += [avg_means_model]
            ret_vars += [avg_vars_model]

        # TODO deal with timestamp data in some way?
        return zip(*ret_means), zip(*ret_vars)

    ##
    # Begin monitoring peception data to make sure it doesn't deviate from
    # the model provided.
    #
    # TODO DOCS
    # @param duration If None, continue capturing until stop is called.
    #                 Else, stop capturing after duration seconds have passed.
    def begin_monitoring(self, perception, mean_model, variance_model, 
                                           std_devs=2.5, duration=None,
                                           contingency=None, contingency_args=None):
        if self.active:
            log("Perception already active.")
            return
        self.active = True

        self.pmonitors[perception] = PeriodicMonitor(self.perceptions[perception], 
                                                     self.rate)

        if duration is None:
            self.pmonitors[perception].start(mean_model, variance_model, std_devs, 
                                             None, contingency, contingency_args)
        else:
            self.pmonitors[perception].start(mean_model, variance_model, std_devs, 
                                             int(duration / self.rate) + 1, 
                                             contingency, contingency_args)

        if not duration is None:
            threading.Timer(self._wait_end_monitoring, duration)

    ##
    # Stop capturing perception data.  Store output data in datasets list for
    # later statistics.
    # TODO DOCS
    def end_monitoring(self):
        if not self.active:
            log("Nothing to stop.")
            return None

        for k in self.perceptions:
            if self.datasets[k] is None:
                self.datasets[k] = [self.pmonitors[k].stop()]
            else:
                self.datasets[k] += [self.pmonitors[k].stop()]
        self.active = False
        return "success"
    
    ##
    # Blocking stop.
    def _wait_end_monitoring(self):
        if not self.active:
            log("Nothing to stop.")
            return

        for k in self.perceptions:
            dataset = None
            while dataset is None:
                dataset = self.pmonitors[k].get_ret_vals()

            if self.datasets[k] is None:
                self.datasets[k] = [dataset]
            else:
                self.datasets[k] += [dataset]
        self.active = False

    # TODO DOCS
    def wait_for_completion(rate=0.01):
        while True:
            for k in self.perceptions:
                if self.pmonitors[k].has_failed():
                    self.active = False
                    return k
            if not self.active:
                return "success"
            rospy.sleep(rate)

if __name__ == '__main__':
    rospy.init_node(node_name, anonymous=True)

    apm = ArmPerceptionMonitor(0, 0.001)
    apm.start_training()
    rospy.sleep(5.)
    apm.stop_training()
    means, vars = apm.generate_model("accelerometer", 100, 50)
    
    xm, ym, zm = zip(*means)
    xv, yv, zv = zip(*vars)
    import matplotlib.pyplot as plt
    plt.subplot(321)
    plt.plot(xm)
    #plt.axis([0, len(xm), 0., 15.])
    plt.title("X mean")
    plt.subplot(323)
    plt.plot(ym)
    plt.title("Y mean")
    plt.subplot(325)
    plt.plot(zm)
    plt.title("Z mean")

    plt.subplot(322)
    plt.plot(xv)
    plt.title("X variance")
    plt.subplot(324)
    plt.plot(yv)
    plt.title("Y variance")
    plt.subplot(326)
    plt.plot(zv)
    plt.title("Z variance")

    plt.show()
