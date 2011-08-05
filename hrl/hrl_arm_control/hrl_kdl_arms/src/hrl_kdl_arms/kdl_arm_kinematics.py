#
# Provides a generic interface for arm kinematics given kdl parameters.
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

# Author: Kelsey Hawkins
import numpy as np
import PyKDL as kdl

import roslib
roslib.load_manifest("hrl_generic_arms")

import rospy

import urdf_parser_python.urdf_parser as urdf
from hrl_generic_arms.hrl_arm_template import HRLArmKinematics

class KDLArmKinematics(HRLArmKinematics):
    def __init__(self, chain, joint_info):
        super(KDLArmKinematics, self).__init__(chain.getNrOfJoints())
        self.chain = chain
        self.joint_info = joint_info

        self.fk_kdl = kdl.ChainFkSolverPos_recursive(self.chain)
        self.ik_v_kdl = kdl.ChainIkSolverVel_pinv(self.chain)
        self.ik_p_kdl = kdl.ChainIkSolverPos_NR(self.chain, self.fk_kdl, self.ik_v_kdl)
        self.jac_kdl = kdl.ChainJntToJacSolver(self.chain)
        self.dyn_kdl = kdl.ChainDynParam(self.chain, kdl.Vector.Zero())

    def FK_vanilla(self, q, link_number=None):
        if link_number is None:
            link_number = self.chain.getNrOfSegments()
        endeffec_frame = kdl.Frame()
        kinematics_status = self.fk_kdl.JntToCart(joint_list_to_kdl(q), endeffec_frame,
                                                  link_number)
        if kinematics_status >= 0:
            p = endeffec_frame.p
            pos = np.mat([p.x(), p.y(), p.z()]).T
            M = endeffec_frame.M
            rot = np.mat([[M[0,0], M[0,1], M[0,2]], 
                          [M[1,0], M[1,1], M[1,2]], 
                          [M[2,0], M[2,1], M[2,2]]])
            return pos, rot
        else:
            return None, None

    def IK_vanilla(self, pos, rot, q_guess=None):
        pos_kdl = kdl.Vector(pos[0,0], pos[1,0], pos[2,0])
        rot_kdl = kdl.Rotation(rot[0,0], rot[0,1], rot[0,2],
                               rot[1,0], rot[1,1], rot[1,2],
                               rot[2,0], rot[2,1], rot[2,2])
        frame_kdl = kdl.Frame(rot_kdl, pos_kdl)

        if q_guess == None:
            q_guess = [0.] * self.n_jts

        q_kdl = kdl.JntArray(self.n_jts)
        q_guess_kdl = joint_list_to_kdl(q_guess)
        if self.ik_p_kdl.CartToJnt(q_guess_kdl, frame_kdl, q_kdl) >= 0:
            return self.normalize_angles(joint_kdl_to_list(q_kdl))
        else:
            return None

    def jacobian_vanilla(self, q, pos=None):
        j_kdl = kdl.Jacobian(self.n_jts)
        q_kdl = joint_list_to_kdl(q)
        self.jac_kdl.JntToJac(q_kdl, j_kdl)
        return kdl_to_mat(j_kdl)

    def inertia(self, q):
        h_kdl = kdl.JntSpaceInertiaMatrix(self.n_jts)
        self.dyn_kdl.JntToMass(joint_list_to_kdl(q), h_kdl)
        return kdl_to_mat(h_kdl)

    def cart_inertia(self, q):
        H = self.inertia(q)
        J = self.jacobian(q)
        return np.linalg.inv(J * np.linalg.inv(H) * J.T)

    def normalize_angles(self, q):
        min_lims = self.joint_info["safe_mins"]
        max_lims = self.joint_info["safe_maxs"]
        q_mod = np.mod(q, 2 * np.pi)
        in_lims_a = np.all([q_mod >= min_lims, q_mod <= max_lims], 0)
        in_lims_b = np.all([(q_mod - 2*np.pi) >= min_lims, (q_mod - 2*np.pi) <= max_lims], 0)
        if np.all(np.any([in_lims_a, in_lims_b],0)):
            return np.where(in_lims_a, q_mod, q_mod - 2 * np.pi)
        return None

    def angles_in_limits(self, q):
        min_lims = self.joint_info["lim_mins"]
        max_lims = self.joint_info["lim_maxs"]
        return np.all([q >= min_lims, q <= max_lims], 0)

    def angles_in_safetys(self, q):
        min_lims = self.joint_info["safe_mins"]
        max_lims = self.joint_info["safe_maxs"]
        return np.all([q >= min_lims, q <= max_lims], 0)

    def random_joint_angles(self):
        min_lims = self.joint_info["safe_mins"]
        max_lims = self.joint_info["safe_maxs"]
        contins = np.array(self.joint_info["types"]) == urdf.Joint.CONTINUOUS
        min_lims = np.where(contins, -np.pi, min_lims)
        max_lims = np.where(contins, np.pi, max_lims)
        zip_lims = zip(min_lims, max_lims)
        return [np.random.uniform(min_lim, max_lim) for min_lim, max_lim in zip_lims]

    def IK_search(self, pos, rot, timeout=1.):
        st_time = rospy.get_time()
        while not rospy.is_shutdown() and rospy.get_time() - st_time < timeout:
            q_init = self.random_joint_angles()
            q_ik = self.IK_vanilla(pos, rot, q_init)
            if q_ik is not None:
                #print "time", rospy.get_time() - st_time
                return q_ik
        return None
        

        
def kdl_to_mat(m):
    mat =  np.mat(np.zeros((m.rows(), m.columns())))
    for i in range(m.rows()):
        for j in range(m.columns()):
            mat[i,j] = m[i,j]
    return mat

def joint_kdl_to_list(q):
    if q == None:
        return None
    return [q[i] for i in range(q.rows())]

def joint_list_to_kdl(q):
    if q is None:
        return None
    q_kdl = kdl.JntArray(len(q))
    for i, q_i in enumerate(q):
        q_kdl[i] = q_i
    return q_kdl