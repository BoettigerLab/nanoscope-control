#!/usr/bin/env python
"""
Camera control specialized for a Hamamatsu camera.

Hazen 09/15
"""
from PyQt5 import QtCore

import storm_control.sc_hardware.hamamatsu.hamamatsu_camera as hcam
import storm_control.sc_library.parameters as params

import storm_control.hal4000.camera.cameraControl as cameraControl
import storm_control.hal4000.camera.cameraFunctionality as cameraFunctionality


class HamamatsuCameraControl(cameraControl.HWCameraControl):
    """
    Interface to a Hamamatsu sCMOS camera.
    """
    def __init__(self, config = None, is_master = False, **kwds):
        kwds["config"] = config
        super().__init__(**kwds)

        # The camera configuration.
        self.camera_functionality = cameraFunctionality.CameraFunctionality(camera_name = self.camera_name,
                                                                            is_master = is_master,
                                                                            parameters = self.parameters)

        # Load the library and start the camera.
        self.camera = hcam.HamamatsuCameraMR(camera_id = config.get("camera_id"))

        # Dictionary of the Hamamatsu camera properties we'll support.
        self.hcam_props = {"binning" : True,
                           "defect_correct_mode" : True,
                           "exposure_time" : True,
                           "output_trigger_kind[0]" : True,
                           "readout_speed" : True,
                           "subarray_hpos" : True,
                           "subarray_hsize" : True,
                           "subarray_vpos" : True,
                           "subarray_vsize" : True,
                           "trigger_source" : True}

        max_intensity = 2**self.camera.getPropertyValue("bit_per_channel")[0]
        self.parameters.setv("max_intensity", max_intensity)

        self.parameters.setv("exposure_time", 0.1)

        x_chip = self.camera.getPropertyValue("image_width")[0]
        y_chip = self.camera.getPropertyValue("image_height")[0]
        self.parameters.setv("x_chip", x_chip)
        self.parameters.setv("y_chip", y_chip)

        text_values = self.camera.sortedPropertyTextOptions("binning")
        self.parameters.add(params.ParameterSetString(description = "Camera binning.",
                                                      name = "binning",
                                                      value = text_values[0],
                                                      allowed = text_values))
        
        text_values = self.camera.sortedPropertyTextOptions("defect_correct_mode")
        self.parameters.add(params.ParameterSetString(description = "Defect correction mode.",
                                                      name = "defect_correct_mode",
                                                      value = text_values[0],
                                                      allowed = text_values))

        # FIXME: Can't save this as the property name is not valid XML.
        text_values = self.camera.sortedPropertyTextOptions("output_trigger_kind[0]")
        self.parameters.add(params.ParameterSetString(description = "Camera 'fire' pin output signal.",
                                                      name = "output_trigger_kind[0]",
                                                      value = text_values[1],
                                                      allowed = text_values,
                                                      is_saved = False))

        self.parameters.add(params.ParameterRangeInt(description = "Read out speed",
                                                     name = "readout_speed",
                                                     value = 2,
                                                     min_value = 1,
                                                     max_value = 2))

        # These all need to multiples of 4.
        self.parameters.add(params.ParameterRangeInt(description = "AOI X start",
                                                     name = "subarray_hpos",
                                                     value = 0, 
                                                     min_value = 0, 
                                                     max_value = (x_chip - 1)))

        self.parameters.add(params.ParameterRangeInt(description = "AOI Width",
                                                     name = "subarray_hsize",
                                                     value = x_chip, 
                                                     min_value = 4, 
                                                     max_value = x_chip))

        self.parameters.add(params.ParameterRangeInt(description = "AOI Y start",
                                                     name = "subarray_vpos",
                                                     value = 0, 
                                                     min_value = 0, 
                                                     max_value = (y_chip - 1)))

        self.parameters.add(params.ParameterRangeInt(description = "AOI Height",
                                                     name = "subarray_vsize",
                                                     value = y_chip, 
                                                     min_value = 4, 
                                                     max_value = y_chip))

        text_values = self.camera.sortedPropertyTextOptions("trigger_source")
        self.parameters.add(params.ParameterSetString(description = "Camera trigger source.",
                                                      name = "trigger_source",
                                                      value = text_values[0],
                                                      allowed = text_values))

        ## Disable editing of the HAL versions of these parameters.
        for param in ["x_bin", "x_end", "x_start", "y_end", "y_start", "y_bin"]:
            self.parameters.getp(param).setMutable(False)

        self.newParameters(self.parameters, initialization = True)

    def newParameters(self, parameters, initialization = False):

        # Translate AOI information to parameters used by HAL.
        # HAL is 1 based, hcam is 0 based.
        binning = int(parameters.get("binning")[0])
        parameters.set("x_bin", binning)
        parameters.set("x_end", parameters.get("subarray_hpos") + parameters.get("subarray_hsize"))
        parameters.set("x_pixels", parameters.get("subarray_hsize"))
        parameters.set("x_start", parameters.get("subarray_hpos") + 1)
        
        parameters.set("y_bin", binning)
        parameters.set("y_end", parameters.get("subarray_vpos") + parameters.get("subarray_vsize"))
        parameters.set("y_pixels", parameters.get("subarray_vsize"))
        parameters.set("y_start", parameters.get("subarray_vpos") + 1)

        # Super class performs some simple checks & update some things.
        super().newParameters(parameters)

        self.camera_working = True

        # Update the parameter values, only the Hamamatsu specific 
        # ones and only if they are different.
        to_change = []
        for pname in self.hcam_props:
            if (self.parameters.get(pname) != parameters.get(pname)) or initialization:
                to_change.append(pname)

        if (len(to_change)>0):
            running = self.running
            if running:
                self.camera_functionality.invalid.emit()
                self.stopCamera()

            for pname in to_change:
                self.camera.setPropertyValue(pname, parameters.get(pname))
                self.parameters.setv(pname, parameters.get(pname))

            if running:
                self.startCamera()

        exposure_time = self.camera.getPropertyValue("exposure_time")[0]
        readout_time = self.camera.getPropertyValue("timing_readout_time")[0]
        if (exposure_time < readout_time):
            fps = 1.0/readout_time
            print(">> Warning! exposure time is shorter than readout time.")
        else:
            fps = 1.0/exposure_time

        self.parameters.setv("exposure_time", exposure_time)
        self.parameters.setv("fps", fps)


#
# The MIT License
#
# Copyright (c) 2015 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

