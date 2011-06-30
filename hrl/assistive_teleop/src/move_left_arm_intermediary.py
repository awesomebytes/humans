#!/usr/bin/python

import roslib; roslib.load_manifest('assistive_teleop')
import rospy
import actionlib
import math
import numpy as np
from geometry_msgs.msg  import PoseStamped
#import sensor_msgs
import move_arm_msgs.msg
import motion_planning_msgs.msg
from kinematics_msgs.srv import GetKinematicSolverInfo, GetPositionFK, GetPositionFKRequest, GetPositionIK, GetPositionIKRequest
from pr2_controllers_msgs.msg import JointTrajectoryAction, JointTrajectoryControllerState, JointTrajectoryActionGoal
from trajectory_msgs.msg import JointTrajectoryPoint
from std_msgs.msg import String, Bool

class MoveLeftArmIntermediary():

    try_per = 1
    move_arm_error_dict = {
         -1 : "PLANNING_FAILED: Could not plan a clear path to goal.",
          1 : "SUCCEEDED",
         -2 : "TIMED_OUT",
         -3 : "START_STATE_IN_COLLISION: Try freeing the arms manually.",
         -4 : "START_STATE_VIOLATES_PATH_CONSTRAINTS",
         -5 : "GOAL_IN_COLLISION",
         -6 : "GOAL_VIOLATES_PATH_CONSTRAINTS",
         -7 : "INVALID_ROBOT_STATE",
         -8 : "INCOMPLETE_ROBOT_STATE",
         -9 : "INVALID_PLANNER_ID",
         -10 : "INVALID_NUM_PLANNING_ATTEMPTS",
         -11 : "INVALID_ALLOWED_PLANNING_TIME",
         -12 : "INVALID_GROUP_NAME",
         -13 : "INVALID_GOAL_JOINT_CONSTRAINTS",
         -14 : "INVALID_GOAL_POSITION_CONSTRAINTS",
         -15 : "INVALID_GOAL_ORIENTATION_CONSTRAINTS",
         -16 : "INVALID_PATH_JOINT_CONSTRAINTS",
         -17 : "INVALID_PATH_POSITION_CONSTRAINTS",
         -18 : "INVALID_PATH_ORIENTATION_CONSTRAINTS",
         -19 : "INVALID_TRAJECTORY",
         -20 : "INVALID_INDEX",
         -21 : "JOINT_LIMITS_VIOLATED",
         -22 : "PATH_CONSTRAINTS_VIOLATED",
         -23 : "COLLISION_CONSTRAINTS_VIOLATED",
         -24 : "GOAL_CONSTRAINTS_VIOLATED",
         -25 : "JOINTS_NOT_MOVING",
         -26 : "TRAJECTORY_CONTROLLER_FAILED",
         -27 : "FRAME_TRANSFORM_FAILURE",
         -28 : "COLLISION_CHECKING_UNAVAILABLE",
         -29 : "ROBOT_STATE_STALE",
         -30 : "SENSOR_INFO_STALE",
         -31 : "NO_IK_SOLUTION: Cannot reach goal configuration.",
         -32 : "INVALID_LINK_NAME",
         -33 : "IK_LINK_IN_COLLISION: Cannot reach goal configuration without contact.",
         -34 : "NO_FK_SOLUTION",
         -35 : "KINEMATICS_STATE_IN_COLLISION",
         -36 : "INVALID_TIMEOUT"
         }
    def __init__(self):
        rospy.init_node('move_left_arm_intermediary')
        self.move_left_arm_client = actionlib.SimpleActionClient('move_left_arm', move_arm_msgs.msg.MoveArmAction)
    #    self.left_arm_traj_client = actionlib.SimpleActionClient('l_arm_controller/joint_trajectory_action', JointTrajectoryAction)

        rospy.Subscriber('l_arm_controller/state', JointTrajectoryControllerState , self.set_joint_state) 
        rospy.Subscriber('wt_left_arm_pose_commands', PoseStamped, self.choose_method)
        rospy.Subscriber('wt_left_arm_angle_commands', JointTrajectoryPoint, self.send_joint_angles)
        rospy.Subscriber('wt_move_left_arm_goals', PoseStamped, self.compose_goal)
    
        self.pose_out = rospy.Publisher('l_hand_pose', PoseStamped)
        self.joints_out = rospy.Publisher('l_arm_controller/joint_trajectory_action/goal', JointTrajectoryActionGoal )
        self.wt_log_out = rospy.Publisher('wt_log_out', String )

        rospy.loginfo("Waiting for move_left_arm server")
        self.move_left_arm_client.wait_for_server()
        rospy.loginfo("Move_left_arm Server found")
    
        rospy.loginfo("Waiting for FK Solver services")
        rospy.wait_for_service('/pr2_left_arm_kinematics/get_fk')
        rospy.wait_for_service('/pr2_left_arm_kinematics/get_fk_solver_info')
        rospy.wait_for_service('/pr2_left_arm_kinematics/get_ik')
        rospy.wait_for_service('/pr2_left_arm_kinematics/get_ik_solver_info')
        self.fk_info_proxy = rospy.ServiceProxy('/pr2_left_arm_kinematics/get_fk_solver_info', GetKinematicSolverInfo)
        self.fk_pose_proxy = rospy.ServiceProxy('/pr2_left_arm_kinematics/get_fk', GetPositionFK)    
        self.ik_info_proxy = rospy.ServiceProxy('/pr2_left_arm_kinematics/get_ik_solver_info', GetKinematicSolverInfo)
        self.ik_pose_proxy = rospy.ServiceProxy('/pr2_left_arm_kinematics/get_ik', GetPositionIK)    
        rospy.loginfo("Service Proxies Established")
        
    def set_joint_state(self,msg):
        self.joint_state = msg.actual.positions;


    def get_fk(self, msg):
        #print "get_fk of %s" %str(msg)
        if (self.joint_state):
            fk_request = GetPositionFKRequest()
            fk_request.header.frame_id = '/torso_lift_link'
            fk_request.fk_link_names =  self.fk_info.kinematic_solver_info.link_names
            fk_request.robot_state.joint_state.position = self.joint_state
            fk_request.robot_state.joint_state.name = self.fk_info.kinematic_solver_info.joint_names
        else:
            rospy.loginfo("No Joint States Available Yet")

        try:
            self.curr_pose = self.fk_pose_proxy(fk_request)
            self.pose_out.publish(self.curr_pose.pose_stamped[-1])
        #    print "Pose from FK: %s" %str(self.curr_pose.pose_stamped[-1])
        except rospy.ServiceException, e:
            rospy.loginfo("FK service did not process request: %s" %str(e))
    
    def get_kin_info(self):
        print "getting ik info"
        try:
            self.ik_info = self.ik_info_proxy();
        except rospy.ServiceException, e:
            rospy.loginfo("IK Service did no process request: %s" %str(e))
        #print "IK Info: %s" %self.ik_info
        
        print "getting fk info"
        try:
            self.fk_info = self.fk_info_proxy();
        except rospy.ServiceException, e:
            rospy.loginfo("FK Service did no process request: %s" %str(e))
        #print "FK Info: %s" %self.fk_info

    def choose_method(self, msg):
        #print self.curr_pose.pose_stamped[-1]
        cur_pos = self.curr_pose.pose_stamped[-1].pose.position
        goal_pos = msg.pose.position
        self.dist = math.sqrt((goal_pos.x - cur_pos.x)**2 +(goal_pos.y - cur_pos.y)**2 + (goal_pos.z - cur_pos.z)**2)
        if (self.dist < 0.25):
            self.wt_log_out.publish(data="Small Move Requested: Trying to move WITHOUT motion planning")    
            self.get_ik(msg)
        else:
            self.wt_log_out.publish(data="Large Move Requested: Trying to move WITH motion planning")    
            self.compose_goal(msg)
    
    def get_ik(self, msg):
        #print "get_ik of %s" %str(msg)
        if (self.joint_state):
            ik_request = GetPositionIKRequest()
            ik_request.timeout = rospy.Duration(5)
            ik_request.ik_request.pose_stamped = msg
            ik_request.ik_request.ik_link_name = self.curr_pose.fk_link_names[-1]
            ik_request.ik_request.ik_seed_state.joint_state.name =  self.ik_info.kinematic_solver_info.joint_names
            ik_request.ik_request.ik_seed_state.joint_state.position =  self.joint_state
        else:
            rospy.loginfo("No Joint States Available Yet")
        #print "IK Request: %s" %str(ik_request)
        try:
            ik_goal = self.ik_pose_proxy(ik_request)
            #print "IK Goal: %s" %str(ik_goal)
            if ik_goal.error_code.val == 1:
                self.try_per = 1;
                self.send_joint_angles(ik_goal)
            else:
                self.try_per -= 0.1
                if (self.try_per >= 0.01):
                    self.wt_log_out.publish(data="Small Move Goal Out of Reach: Trying to reach part of the way")
                    goal_pos = msg.pose.position
                    curr_pos = self.curr_pose.pose_stamped[-1].pose.position
                    goal_pos.x = curr_pos.x + self.try_per*(goal_pos.x-curr_pos.x)
                    goal_pos.y = curr_pos.y + self.try_per*(goal_pos.y-curr_pos.y)
                    goal_pos.z = curr_pos.z + self.try_per*(goal_pos.z-curr_pos.z)
                    msg.pose.position = goal_pos
                    self.get_ik(msg)
                else:   
                    rospy.loginfo("IK Failed: Error Code %s" %str(ik_goal.error_code))
                    self.wt_log_out.publish(data="Inverse Kinematics Failed: Goal Out of Reach.")   
            
        except rospy.ServiceException, e:
            rospy.loginfo("IK service did not process request: %s" %str(e))


    def send_joint_angles(self, goal):
        print "send_joint_angles: %s" %str(goal)
        point = JointTrajectoryPoint()
        
        if isinstance(goal,type(point)):
            #print "Wrist Goal: %s" %str(goal)
            point = goal
            self.dist = 0.1
        else:
            #print "Arm Goal"
            point.positions = goal.solution.joint_state.position
        point.time_from_start = rospy.Duration(self.dist/0.05)
        
        joints_goal = JointTrajectoryActionGoal()
        joints_goal.goal.trajectory.joint_names = self.ik_info.kinematic_solver_info.joint_names
        joints_goal.goal.trajectory.points.append(point)

    #    print "Final Goal: %s" %str(joints_goal)

        self.joints_out.publish(joints_goal)

    def compose_goal(self, goal_in):
        rospy.loginfo("composing move_left_arm goal")

        goal_out = move_arm_msgs.msg.MoveArmGoal()

        goal_out.motion_plan_request.group_name = "left_arm"
        goal_out.motion_plan_request.num_planning_attempts = 1
        goal_out.motion_plan_request.planner_id = ""
        goal_out.planner_service_name = "ompl_planning/plan_kinematic_path"
        goal_out.motion_plan_request.allowed_planning_time = rospy.Duration(5.0)
        
        pos = motion_planning_msgs.msg.PositionConstraint()
        pos.header.frame_id = goal_in.header.frame_id 
        pos.link_name="l_wrist_roll_link"
        pos.position.x = goal_in.pose.position.x 
        pos.position.y = goal_in.pose.position.y
        pos.position.z = goal_in.pose.position.z

        pos.constraint_region_shape.type = 0 
        pos.constraint_region_shape.dimensions=[0.05]

        pos.constraint_region_orientation.x = 0
        pos.constraint_region_orientation.y = 0
        pos.constraint_region_orientation.z = 0
        pos.constraint_region_orientation.w = 1
        pos.weight = 1

        goal_out.motion_plan_request.goal_constraints.position_constraints.append(pos)
    
        ort = motion_planning_msgs.msg.OrientationConstraint()    
        ort.header.frame_id=goal_in.header.frame_id
        ort.link_name="l_wrist_roll_link"
        ort.orientation.x = goal_in.pose.orientation.x
        ort.orientation.y = goal_in.pose.orientation.y
        ort.orientation.z = goal_in.pose.orientation.z
        ort.orientation.w = goal_in.pose.orientation.w
        
        ort.absolute_roll_tolerance = 0.04
        ort.absolute_pitch_tolerance = 0.04
        ort.absolute_yaw_tolerance = 0.04
        ort.weight = 0.5

        goal_out.motion_plan_request.goal_constraints.orientation_constraints.append(ort)
        rospy.loginfo("sending composed move_left_arm goal")

    
        finished_within_time = False
        self.move_left_arm_client.send_goal(goal_out)
        finished_within_time = self.move_left_arm_client.wait_for_result(rospy.Duration(30))
        if not (finished_within_time):
            self.move_left_arm_client.cancel_goal()
            self.wt_log_out.publish(data="Timed out achieving left arm goal pose")   
            rospy.loginfo("Timed out achieving left arm goal pose")
        else:
            state = self.move_left_arm_client.get_state()
            result = self.move_left_arm_client.get_result()
            if (state == 3): #3 == SUCCEEDED
               rospy.loginfo("Action Finished: %s" %state)
               self.wt_log_out.publish(data="Move Left Arm with Motion Planning: %s" %self.move_arm_error_dict[result.error_code.val])   
            else:
                if result.error_code.val != 1:
                    rospy.loginfo("Move_left_arm action failed: %s" %state)
                    rospy.loginfo("Failure Result: %s" %result)
                    self.wt_log_out.publish(data="Move Left Arm with Motion Planning: Failed: %s" %self.move_arm_error_dict[result.error_code.val])   
                else:
                    rospy.loginfo("Move_left_arm_action failed: Unable to plan a path to goal")
                    self.wt_log_out.publish(data="Move Left Arm with Motion Planning: Failed: Unable to plan a path to the goal")
                     
if __name__ == '__main__':
    MLAI = MoveLeftArmIntermediary()
    MLAI.get_kin_info()

    r = rospy.Rate(10)
    while not rospy.is_shutdown():
        MLAI.get_fk(MLAI.joint_state)

        r.sleep()
