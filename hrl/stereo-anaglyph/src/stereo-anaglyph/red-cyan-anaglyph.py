import roslib
roslib.load_manifest('stereo-anaglyph')
import rospy
import hrl_camera.ros_camera as rc
import cv

def add_alpha_channel(bgr, alpha_val):
    w, h = cv.GetSize(bgr)
    bgra  = cv.CreateImage((w, h), cv.IPL_DEPTH_8U, 4)
    alpha = cv.CreateImage((w, h), cv.IPL_DEPTH_8U, 1)
    chan1 = cv.CreateImage((w, h), cv.IPL_DEPTH_8U, 1)
    chan2 = cv.CreateImage((w, h), cv.IPL_DEPTH_8U, 1)
    chan3 = cv.CreateImage((w, h), cv.IPL_DEPTH_8U, 1)
    cv.Split(bgr, chan1, chan2, chan3, None)
    cv.Set(alpha, (alpha_val))
    cv.Merge(chan1, chan2, chan3, alpha, bgra)
    return bgra


def remove_channels(in_bgra, channel_indices):
    w, h = cv.GetSize(in_bgra)
    chan1 = cv.CreateImage((w,h), cv.IPL_DEPTH_8U, 1)
    chan2 = cv.CreateImage((w,h), cv.IPL_DEPTH_8U, 1)
    chan3 = cv.CreateImage((w,h), cv.IPL_DEPTH_8U, 1)
    chan4 = cv.CreateImage((w,h), cv.IPL_DEPTH_8U, 1)
    bgra  = cv.CreateImage((w,h), cv.IPL_DEPTH_8U, 4)

    cv.Split(in_bgra, chan1, chan2, chan3, chan4)
    chan_list = [chan1, chan2, chan3, chan4]
    for i in channel_indices:
        chan_list[i] = None
    chan_list.append(bgra)
    cv.Merge(*tuple(chan_list))
    return bgra


def anaglyph(left_color, right_color, correction):
    #create oversized image
    #result = cv.CreateImage(cv.GetSize(right_color), cv.IPL_DEPTH_8U, 4)
    w, h = cv.GetSize(left_color)
    bgra = cv.CreateImage((w*2, h), cv.IPL_DEPTH_8U, 4)
    right_bgra = add_alpha_channel(right_color, round(255/2.)) #cyan (remove red?)
    left_bgra  = add_alpha_channel(left_color, round(255/2.)) #red (remove blue?, green?)

    #remove blue & green from left => red
    left_red = remove_channels(left_bgra, [0, 1])
    #remove red from right_bgra => cyan
    right_cyan = remove_channels(right_bgra, [2])

    #copy left & right onto bgra
    left_area = cv.GetSubRect(bgra, (0,0,w,h))
    cv.Add(left_red, left_area, left_area)

    right_area = cv.GetSubRect(bgra, (correction, 0, w, h))
    cv.Add(right_cyan, right_area, right_area)

    valid_area = cv.GetSubRect(bgra, (correction, 0, w - correction, h))
    return valid_area


cameras = ['/wide_stereo/left/image_rect_color', 
           '/wide_stereo/right/image_rect_color']
stereo_listener = rc.ROSStereoListener(cameras)
cv.NamedWindow('stereo-anaglyph', cv.CV_WINDOW_AUTOSIZE)
cv.WaitKey(10)
anaglyph_cyan_image_distance_correction = rospy.get_param('anaglyph_dist', 30)


while not rospy.is_shutdown():
    l, r = stereo_listener.next()
    red_blue = anaglyph(l, r, anaglyph_cyan_image_distance_correction)
    cv.ShowImage('stereo-anaglyph', red_blue)
    cv.WaitKey(10)

































#from opencv import cv
#from opencv import highgui
#from time import sleep
#
#def makeMagic(left, right, out):
#    chans=[]
#    for i in range(6):
#        chans.append(cv.cvCreateImage(cv.cvGetSize(left),8,1))
#    cv.cvSplit(left, chans[0], chans[1], chans[2], None);
#    cv.cvSplit(right, chans[3], chans[4], chans[5], None);
#    cv.cvMerge(chans[3],chans[4],chans[2], None, out);
#    
#    #cv.cvMerge(None,chans[1],None, None, out);
#
#cam=[]
#def main():
#    cam.append(highgui.cvCreateCameraCapture(0))
#    cam.append(highgui.cvCreateCameraCapture(1))
#    highgui.cvNamedWindow ("carrots", highgui.CV_WINDOW_AUTOSIZE)
#
#    uno=highgui.cvQueryFrame(cam[0]);
#    dos=highgui.cvQueryFrame(cam[1]);
#
#    highgui.cvShowImage("carrots",uno);
#    highgui.cvWaitKey(0);
#    highgui.cvShowImage("carrots",dos);
#    highgui.cvWaitKey(0);
#
#    merge=cv.cvCreateImage(cv.cvGetSize(uno),8,3)
#    makeMagic(uno, dos, merge)
#
#    highgui.cvShowImage("carrots",merge);
#    highgui.cvWaitKey(0);
#
#    while True :
#        uno=highgui.cvQueryFrame(cam[0]);
#        dos=highgui.cvQueryFrame(cam[1]);
#        makeMagic(uno, dos, merge);
#        highgui.cvShowImage("carrots",merge);
#        if highgui.cvWaitKey(1)=="s":
#          cam.append(cam.pop(0))
#        print "tick"
#
#if __name__=="__main__":
#  main()
