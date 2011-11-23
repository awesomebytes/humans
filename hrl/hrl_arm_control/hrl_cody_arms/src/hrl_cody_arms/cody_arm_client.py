#
# subscribe to thw joint angles and raw forces topics,  and provide FK
# etc.
#
# Copyright (c) 2009, Georgia Tech Research Corporation
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Georgia Tech Research Corporation nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY GEORGIA TECH RESEARCH CORPORATION ''AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL GEORGIA TECH BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

# Author: Advait Jain

import math
import numpy as np
import copy
import sys

import roslib; roslib.load_manifest('hrl_cody_arms')
import rospy

from cody_arm_kinematics import CodyArmKinematics
from equilibrium_point_control.hrl_arm import HRLArm
import hrl_lib.viz as hv

from hrl_msgs.msg import FloatArray
from std_msgs.msg import Header, Bool, Empty

from visualization_msgs.msg import Marker


# used in client and server.
def get_joint_name_list(arm):
    if arm == 'r':
        return ['m3joint_ma1_j%d'%i for i in range(7)]
    else:
        return ['m3joint_ma2_j%d'%i for i in range(7)]


class CodyArmClient(HRLArm):
    # arm - 'r' or 'l'
    def __init__(self, arm):
        kinematics = CodyArmKinematics(arm)
        HRLArm.__init__(self, kinematics)
        self.alpha = None
        self.ft_val = None
        self.pwr_state = False

        self.fts_bias = {'force': np.matrix(np.zeros(3)).T,
                         'torque': np.matrix(np.zeros(3)).T}

        self.joint_names_list = get_joint_name_list(arm)

        self.jep_cmd_pub = rospy.Publisher('/'+arm+'_arm/command/jep', FloatArray)
        self.alph_cmd_pub = rospy.Publisher('/'+arm+'_arm/command/joint_impedance_scale',
                                            FloatArray)
        self.stop_pub = rospy.Publisher('/arms/stop', Empty)
        self.motors_off_pub = rospy.Publisher('/arms/command/motors_off', Empty)

        self.marker_pub = rospy.Publisher('/'+arm+'_arm/viz/markers', Marker)

        rospy.Subscriber('/'+arm+'_arm/jep', FloatArray, self.ep_cb)
        rospy.Subscriber('/'+arm+'_arm/joint_impedance_scale', FloatArray, self.alpha_cb)

        rospy.Subscriber('/'+arm+'_arm/q', FloatArray, self.q_cb)
        rospy.Subscriber('/'+arm+'_arm/qdot', FloatArray, self.qdot_cb)

        rospy.Subscriber('/'+arm+'_arm/force', FloatArray, self.force_cb)
        rospy.Subscriber('/'+arm+'_arm/force_raw', FloatArray, self.raw_force_cb)

        rospy.Subscriber('/arms/pwr_state', Bool, self.pwr_state_cb)

        try:
            rospy.init_node(arm+'_arm_client', anonymous=False)
        except rospy.ROSException:
            pass

    #---------- ROS callbacks -----------------
    def pwr_state_cb(self, msg):
        with self.lock:
            self.pwr_state = msg.data

    def ep_cb(self, msg):
        with self.lock:
            self.ep = copy.copy(msg.data)

    def alpha_cb(self, msg):
        with self.lock:
            self.alpha = copy.copy(msg.data)

    def q_cb(self, msg):
        with self.lock:
            self.q = copy.copy(msg.data)

    def qdot_cb(self, msg):
        with self.lock:
            self.qdot = copy.copy(msg.data)

    def force_cb(self, msg):
        with self.lock:
            self.ft_val = copy.copy(msg.data)

    def raw_force_cb(self, msg):
        with self.lock:
            self.raw_force = copy.copy(msg.data)

    #--------- functions to use -----------------

    def publish_rviz_markers(self):
        # publish the CEP marker.
        o = np.matrix([0.,0.,0.,1.]).T
        jep = self.get_ep()
        cep, r = self.kinematics.FK(jep)
        cep_marker = hv.single_marker(cep, o, 'sphere',
                        '/torso_lift_link', color=(0., 0., 1., 1.),
                        scale = (0.02, 0.02, 0.02), duration=0.,
                        m_id=1)
        cep_marker.header.stamp = rospy.Time.now()
        self.marker_pub.publish(cep_marker)

        q = self.get_joint_angles()
        ee, r = self.kinematics.FK(q)
        ee_marker = hv.single_marker(ee, o, 'sphere',
                        '/torso_lift_link', color=(0., 1., 0., 1.),
                        scale = (0.02, 0.02, 0.02), duration=0.,
                        m_id=2)
        ee_marker.header.stamp = rospy.Time.now()
        self.marker_pub.publish(ee_marker)


    def get_wrist_force(self, bias=True, base_frame=True,
                        filtered = True):
        with self.lock:
            if filtered:
                f = copy.copy(self.ft_val)
            else:
                f = copy.copy(self.raw_force)

        f_mat = np.matrix(f).T
        f_mat = f_mat[0:3,:] # ignoring the torques.

        if bias:
            f_mat = f_mat - self.fts_bias['force']  #Tiffany added an 's' to 'ft'
        
        if base_frame:
            q = self.get_joint_angles()
            rot = self.kinematics.FK(q)[1]
            f_mat = rot*f_mat
        return f_mat
            
    def bias_wrist_ft(self):
        f_list = []
        t_list = []
        rospy.loginfo('Starting biasing...')
        for i in range(20):
            f_list.append(self.get_wrist_force(bias=False,
                                        base_frame=False))
            rospy.sleep(0.02)

        f_b = np.mean(np.column_stack(f_list), 1)
        # torque is unimplemented.
        t_b = self.get_wrist_torque(bias=False) #Tiffany Nov 8 2011 removed 'arm' arg
        self.fts_bias['force'] = f_b
        self.fts_bias['torque'] = t_b                
        rospy.loginfo('...done')

    # @return array-like of floats b/w 0 and 1.
    def get_impedance_scale(self):
        with self.lock:
            sc = copy.copy(self.alpha)
        return sc

    # @param s - list of floats b/w 0 and 1.
    def set_impedance_scale(self, s):
        time_stamp = rospy.Time.now()
        h = Header()
        h.stamp = time_stamp
        self.alph_cmd_pub.publish(FloatArray(h, s))

    # @param duration - for compatibility with the PR2 class.
    def set_ep(self, jep, duration=None):
        time_stamp = rospy.Time.now()
        h = Header()
        h.stamp = time_stamp
        self.jep_cmd_pub.publish(FloatArray(h, jep))
        self.publish_rviz_markers()

    def is_motor_power_on(self):
        return self.pwr_state

    def motors_off(self):
        self.motors_off_pub.publish()


    #-------- unimplemented functions -----------------

    # leaving this unimplemented for now. Advait Nov 14, 2010.
    def get_joint_accelerations(self, arm):
        pass

    # leaving this unimplemented for now. Advait Nov 14, 2010.
    def get_joint_torques(self, arm):
        pass

    # leaving this unimplemented for now. Advait Nov 14, 2010.
    def get_wrist_torque(self, bias=True):  #Tiffany Nov 8 2011 removed 'arm' arg
        pass


if __name__ == '__main__':
    import m3.toolbox as m3t
    import hrl_lib.transforms as tr
    import optparse

    p = optparse.OptionParser()
    p.add_option('--arm_to_use', action='store', dest='arm',
                 type='string', help='which arm to use (l or r)',
                 default=None)
    opt, args = p.parse_args()

    if opt.arm == None:
        print 'Please specify an arm_to_use'
        print 'Exiting...'
        sys.exit()

    ac = CodyArmClient(opt.arm)

    # print FT sensor readings.
    if False:
        ac.bias_wrist_ft()
        while not rospy.is_shutdown():
            f = ac.get_wrist_force()
            print 'f:', f.A1
            rospy.sleep(0.05)

    if True:
        while not rospy.is_shutdown():
            #jep = ac.get_ep()
            #print 'jep:', jep
            q = ac.get_joint_angles()
            print 'q:', np.degrees(q).tolist()[1]
            rospy.sleep(0.05)

    if False:
        while not rospy.is_shutdown():
            qdot = ac.get_joint_velocities()
            print 'qdot:', np.degrees(qdot)
            rospy.sleep(0.05)

    if False:
        rospy.sleep(1.)
        isc =  ac.get_impedance_scale()
        print isc
        isc[1] = 0.3
        ac.set_impedance_scale(isc)
        rospy.sleep(1.)
        isc =  ac.get_impedance_scale()
        print isc




#=== Functions that should be in equilibrium_point_control samples ===

#    ##
#    #Function that commands the arm(s) to incrementally move to a jep
#    #@param speed the max angular speed (in radians per second)
#    #@return 'reach'
#    def go_jep(self, arm, q, stopping_function=None, speed=math.radians(30)):
#        if speed>math.radians(90.):
#            speed = math.radians(90.)
#
#        qs_list,qe_list,ns_list,qstep_list = [],[],[],[]
#        done_list = []
#        time_between_cmds = 0.025
#        
#        #qs = np.matrix(self.get_joint_angles(arm))
#        qs = np.matrix(self.get_jep(arm))
#        qe = np.matrix(q)
#        max_change = np.max(np.abs(qe-qs))
#
#        total_time = max_change/speed
#        n_steps = int(total_time/time_between_cmds+0.5)
#
#        qstep = (qe-qs)/n_steps
#
#        if stopping_function != None:
#            done = stopping_function()
#        else:
#            done = False
#
#        step_number = 0
#        t0 = rospy.Time.now().to_time()
#        t_end = t0
#        while done==False:
#            t_end += time_between_cmds
#            t1 = rospy.Time.now().to_time()
#
#            if stopping_function != None:
#                done = stopping_function()
#            if step_number < n_steps and done == False:
#                q = (qs + step_number*qstep).A1.tolist()
#                self.set_jep(arm, q)
#            else:
#                done = True
#
#            while t1 < t_end:
#                if stopping_function != None:
#                    done = done or stopping_function()
#                rospy.sleep(time_between_cmds/5)
#                t1 = rospy.Time.now().to_time()
#            step_number += 1
#
#        rospy.sleep(time_between_cmds)
#        return 'reach'
#
#    def go_cep(self, arm, p, rot, speed = 0.10,
#                     stopping_function = None, q_guess = None):
#        q = self.arms.IK(arm, p, rot, q_guess)
#        if q == None:
#            print 'IK soln NOT found.'
#            print 'trying to reach p= ', p
#            return 'fail'
#        else:
#            q_start = np.matrix(self.get_joint_angles(arm))
#            p_start = self.arms.FK(arm, q_start.A1.tolist())
#            q_end = np.matrix(q)
#    
#            dist = np.linalg.norm(p-p_start)
#            total_time = dist/speed
#            max_change = np.max(np.abs(q_end-q_start))
#            ang_speed = max_change/total_time
#            return self.go_jep(arm, q, stopping_function, speed=ang_speed)
#
#    ##
#    # linearly interpolates the commanded cep.
#    # @param arm - 'left_arm' or 'right_arm'
#    # @param p - 3x1 np matrix
#    # @param rot - rotation matrix
#    # @param speed - linear speed (m/s)
#    # @param stopping_function - returns True or False
#    # @return string (reason for stopping)
#    def go_cep_interpolate(self, arm, p, rot=None, speed=0.10,
#                                 stopping_function=None):
#        rot = None # Rotational interpolation not implemented right now.
#        time_between_cmds = 0.025
#
#        q_guess = self.get_jep(arm)
#        cep = self.arms.FK(arm, q_guess)
#        if rot == None:
#            rot = self.arms.FK_rot(arm, q_guess)
#
#        vec = p-cep
#        dist = np.linalg.norm(vec)
#        total_time = dist/speed
#        n_steps = int(total_time/time_between_cmds + 0.5)
#        vec = vec/dist
#        vec = vec * speed * time_between_cmds
#        
#        pt = cep
#        all_done = False
#        i = 0 
#        t0 = rospy.Time.now().to_time()
#        t_end = t0
#        while all_done==False:
#            t_end += time_between_cmds
#            t1 = rospy.Time.now().to_time()
#            pt = pt + vec
#            q = self.arms.IK(arm, pt, rot, q_guess)
#
#            if q == None:
#                all_done = True
#                stop = 'IK fail'
#                continue
#            self.set_jep(arm, q)
#            q_guess = q
#            while t1<t_end:
#                if stopping_function != None:
#                    all_done = stopping_function()
#                if all_done:
#                    stop = 'Stopping Condition'
#                    break
#                rospy.sleep(time_between_cmds/5)
#                t1 = rospy.Time.now().to_time()
#
#            i+=1
#            if i == n_steps:
#                all_done = True
#                stop = ''
#        return stop
#
#    ##  
#    # @param vec - displacement vector (base frame)
#    # @param q_guess - previous JEP?
#    # @return string
#    def move_till_hit(self, arm, vec=np.matrix([0.3,0.,0.]).T, force_threshold=3.0,
#                      speed=0.1, bias_FT=True):
#        unit_vec =  vec/np.linalg.norm(vec)
#        def stopping_function():
#            force = self.get_wrist_force(arm, base_frame = True)
#            force_projection = force.T*unit_vec *-1 # projection in direction opposite to motion.
#            if force_projection>force_threshold:
#                return True
#            elif np.linalg.norm(force)>45.:
#                return True
#            else:
#                return False
#
#        jep = self.get_jep(arm)
#        cep, rot = self.arms.FK_all(arm, jep)
#
#        if bias_FT:
#            self.bias_wrist_ft(arm)
#        rospy.sleep(0.5)
#
#        p = cep + vec
#        return self.go_cep_interpolate(arm, p, rot, speed,
#                                       stopping_function)
#




