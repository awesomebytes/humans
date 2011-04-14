/*********************************************************************
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2010, Willow Garage, Inc.
 *  All rights reserved.
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *   * Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above
 *     copyright notice, this list of conditions and the following
 *     disclaimer in the documentation and/or other materials provided
 *     with the distribution.
 *   * Neither the name of the Willow Garage nor the names of its
 *     contributors may be used to endorse or promote products derived
 *     from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 *  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 *  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 *  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 *  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 *  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 *  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 *  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 *  POSSIBILITY OF SUCH DAMAGE.
 *********************************************************************/

/*
  Author: Daniel Hennes
 */

#include <ros/ros.h>
#include <sensor_msgs/JointState.h>
#include <inverse_dynamics/JointState.h>

#include "inverse_dynamics/SolverNode.h"
#include "inverse_dynamics/InverseDynamicsSolverWBC.h"

int main( int argc, char** argv )
{
  ros::init(argc, argv, "solver_node");
  ros::NodeHandle n("~");

  std::string sai_xml_fname;
  n.param("sai_xml", sai_xml_fname, std::string("robot.sai.xml"));

  XmlRpc::XmlRpcValue joint_list;
  std::vector<std::string> joint_names;

  n.getParam("joints", joint_list);
  ROS_ASSERT(joint_list.getType() == XmlRpc::XmlRpcValue::TypeArray);
  for (int32_t i = 0; i < joint_list.size(); i++) {
    ROS_ASSERT(joint_list[i].getType() == XmlRpc::XmlRpcValue::TypeString);
    joint_names.push_back(static_cast<std::string>(joint_list[i]));
  }

  InverseDynamicsSolverWBC solver = 
    InverseDynamicsSolverWBC(sai_xml_fname);

  SolverNode solver_node(solver, joint_names);
  
  ros::spin();
}
