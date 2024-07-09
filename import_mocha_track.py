'''
Script Name: Import Mocha Track
Script Version: 0.1.1
Flame Version: 2023
Written by: Andrew Miller
Creation Date: 7.21.23

Custom Action Type: Action

Description:

    Imports a planar track from Mocha as either a perspective grid or the UVs of a bilinear surface.

To use:
    
    --In Mocha, set the s-box corners to where you'd like the corners of your perspective grid or surface to live.

    --Export track as 'Autodesk IFFFSE Point Tracker Data (*.ascii)

    --In Flame, right click on the schematic background of an action/gmask tracer/image node

    --From the 'Import Mocha Track' menu, select desired import type


To install:

    Copy script into /opt/Autodesk/shared/python/import_mocha_track
'''


#           Imports             #
# ----------------------------- #

import os, shutil
from pyflame_lib_import_mocha_track import PyFlameFunctions

#         Main Script           #
# ----------------------------- #

SCRIPT_NAME = 'Import Mocha Track'
SCRIPT_PATH = '/opt/Autodesk/shared/python/import_mocha_track'
VERSION = 'v0.1.1'

class MochaTrack():
    def __init__(self):
        import flame

        # Get host node

        self.host_node = flame.batch.current_node.get_value()
        self.host_node_type = str(self.host_node.type)[1:-1]

        # Get start frame

        self.start_frame = flame.batch.start_frame.get_value()
        self.sf_offset = self.start_frame - 1

        # Temp folder for saving node setup

        self.temp_folder = os.path.join(SCRIPT_PATH, 'temp')

        # Selected node variables

        self.host_node_name = self.host_node.name.get_value()
        self.save_node_path = os.path.join(self.temp_folder, self.host_node_name)

        if self.host_node_type == 'Action':
            self.node_filename = self.save_node_path + '.action'
        elif self.host_node_type == 'Image' :
            self.node_filename = self.save_node_path + '.image'
        else:
            self.node_filename = self.save_node_path + '.mask'

        #init instance vars

        self.track_name = ''
        self.lower_left = []
        self.lower_right = []
        self.upper_left = []
        self.upper_right = []
        self.corners = {}

    def import_perspective_grid(self) :
        import flame
        
        pen = self.host_node.cursor_position

        # Read in mocha track
        self.parse_mocha_files()

        # create new perspective grid to animate at the cursor position, named off the mocha tracker files
        blank_grid = self.host_node.create_node('Perspective Grid')

        node_name = self.name_import(self.track_name)
        blank_grid.name = node_name
        
        blank_grid.pos_x, blank_grid.pos_y = pen

        # Save node setup
        self.save_selected_node()

        # Load each line of setup file into list 'contents'

        with open(self.node_filename, 'r') as edit_node:
            contents = edit_node.readlines()

        # Fetch resolution from the setup file

        width_line = self.find_line('FrameWidth', contents)
        width = int(contents[width_line].split()[1])
        
        height_line = self.find_line_after('FrameHeight', width_line, contents)
        height = int(contents[height_line].split()[1])

        # Change perspective grid type to 2D
        # this is necessary for stabilize --> destabilize workflows 
        # change back to 3D in the GUI if undesired

        grid_line = self.find_line(node_name, contents)
        grid_3d_line = self.find_line_after('TransformIs3D', grid_line, contents)
        contents[grid_3d_line] = '\t\tTransformIs3D no\n'

        # Translate mocha corners' x,y coordinates to their flame equivalent
        # Offsetting mocha's position indexes (0,0 = lower left corner) 
        # to match flame's perspective grid (0,0 = center)

        h_offset = width // 2
        v_offset = height // 2

        for key in self.corners :
            translation = []

            for i in self.corners[key] :
                f, xo, yo = i
                tf = (f, float(xo - h_offset + 0.5), float(yo - v_offset + 0.5))
                translation.append(tf)

            x = self.extract_dimension(translation, 'x')
            y = self.extract_dimension(translation, 'y')

            # Add animation from current corner to setup list
            contents = self.add_animation(node_name, contents, f'{key}_corner/x', x)
            contents = self.add_animation(node_name, contents, f'{key}_corner/y', y)

        # Write the modified setup list back to setup file

        with open(self.node_filename, 'w') as edit_node :
            for l in contents :
                edit_node.write(l)

        # Reload saved node

        self.reload_selected_node()

        # Remove temp folder

        self.remove_temp_folder()

        PyFlameFunctions.message_print(f'Perspective Grid "{self.track_name}" loaded', SCRIPT_NAME)
        
    def import_bilinear_uvs(self) :
        import flame
        
        pen = self.host_node.cursor_position 

        # Read in mocha track
        self.parse_mocha_files()

        # create new surface to animate at the cursor position, named off the mocha tracker files

        surface = self.host_node.create_node('Surface')

        node_name = self.name_import(self.track_name)
        surface.name = node_name

        surface.pos_x, surface.pos_y = pen
        parent_axis = self.host_node.nodes[-2]
        parent_axis.pos_x, parent_axis.pos_y = surface.pos_x, surface.pos_y + 125

        # Save node setup

        self.save_selected_node()

        # Load each line of setup file into list 'contents'

        with open(self.node_filename, 'r') as edit_node:
            contents = edit_node.readlines()

        # Change surface type to Bilinear
        # can be changed to perspective or extended bicubic after import in GUI

        name_line = self.find_line(node_name, contents)
        contents[name_line - 1] = 'Node SurfaceBilinear\n'

        # Fetch resolution from the setup file

        width_line = self.find_line_after('ResWidth', name_line, contents)
        width = int(contents[width_line].split()[1])
        
        height_line = self.find_line_after('ResHeight', width_line, contents)
        height = int(contents[height_line].split()[1])

        # add tracker attachments for each corner
        #      --these are essentially inserting the Stabilizer setups for each corner
        
        input_line = self.find_line_after('IsSoftImported', name_line, contents) + 1

        tracker_ll = self.add_tracker('offset0_0', self.lower_left, width, height)
        tracker_ul = self.add_tracker('offset0_1', self.upper_left, width, height)
        tracker_lr = self.add_tracker('offset1_0', self.lower_right, width, height)
        tracker_ur = self.add_tracker('offset1_1', self.upper_right, width, height)

        tracker_attachments = [*tracker_ll, *tracker_ul, *tracker_lr, *tracker_ur]

        for line_num, line_val in enumerate(tracker_attachments, input_line) :
            contents.insert(line_num, line_val)

        track_points_line = self.find_line_after('NumUVTrackControlPoints', input_line, contents)
        contents[track_points_line] = '\t\tNumUVTrackControlPoints 4\n'

        for n in range(4) :
            uvt_line = track_points_line + 1 + n
            contents.insert(uvt_line, f'\t\tUVTrackControlPoint {n}\n')

        # Add ainmation for the uv shape channel. 
        #      value of each frame is an integer index, much like a gmask shape channel

        shapes = [(frame_tup[0], index) for index, frame_tup in enumerate(self.lower_left)]
        contents = self.add_animation(node_name, contents, 'uv_track_shape', shapes, value_lock=True, extrapolation='constant', curve_order='linear')
        
        # Remove the empty 'uv_track_vertices' channel
        # We will replace with individual channels for each corner's x and y position

        track_vertices_line = self.find_line_after('uv_track_vertices', uvt_line, contents)

        while 'End' not in contents[track_vertices_line] :
            contents.pop(track_vertices_line)
        contents.pop(track_vertices_line)

        def channel_lines(corner):
            # Creates a set of empty animation channels based on the corner name passed

            if 'left' in corner :
                horz_direction = 'right'
            else :
                horz_direction = 'left'

            if 'lower' in corner :
                vert_direction = 'up'
            else :
                vert_direction = 'down'

            subchannel_names = ['position/x', 
                                'position/y', 
                                f'horz_tan_{horz_direction}/x', 
                                f'horz_tan_{horz_direction}/y', 
                                'horz_tan_cont', 
                                f'vert_tan_{vert_direction}/x', 
                                f'vert_tan_{vert_direction}/y', 
                                'vert_tan_cont']
            
            ch_lines = []

            for subchannel in subchannel_names :
                if 'cont' in subchannel : val = 2 
                else : val = 0

                lines = [
                    f'\t\tChannel uv_track_vertices/{corner}/{subchannel}\n',
                    '\t\t\tExtrapolation constant\n',
                    f'\t\t\tValue {val}\n',
                    '\t\t\tEnd\n']

                for ln in lines: 
                    ch_lines.append(ln)

            return ch_lines

        # Create all needed channels with channel_lines() and add them to our setup list

        empty_channels = [*channel_lines('lower_left'), *channel_lines('upper_left'), *channel_lines('lower_right'), *channel_lines('upper_right')]

        for setup_line_num, empty_channel_line in enumerate(empty_channels, track_vertices_line) :
            contents.insert(setup_line_num, empty_channel_line)

        # Offset corner animation values based on flame's expected indexes
        # the channel names in original_path_channels all index the same way as Mocha, with 0,0 in the lower left
        # the remaining channels index in reverse, ie. for x channels flameX = mochaX - width, for y channels flameY = mochaY - height 
        
        original_path_channels = ['lower_left/position/x', 'lower_left/position/y', 'upper_left/position/x', 'lower_right/position/y']

        for key in self.corners.keys() :

            x = self.extract_dimension(self.corners[key], 'x')
            y = self.extract_dimension(self.corners[key], 'y')

            channel_names = [f'{key}/position/x', f'{key}/position/y']

            x_translation = []
            y_translation = []

            for ch_dimension in channel_names :
                if ch_dimension in original_path_channels : 
                    if ch_dimension.endswith('x') :
                        for kf in x :
                            tf = (kf[0], kf[1] + 0.5)
                            x_translation.append(tf)
                    else :
                        for kf in y :
                            tf = (kf[0], kf[1] + 0.5)
                            y_translation.append(tf)

                else :
                    if ch_dimension.endswith('x') :
                        for kf in x :
                            tf = (kf[0], kf[1] - width - 0.5)
                            x_translation.append(tf)
                    else :
                        for kf in y :
                            tf = (kf[0], kf[1] - height - 0.5)
                            y_translation.append(tf)

            # Add animation from current corner to setup list
            contents = self.add_animation(node_name, contents, f'uv_track_vertices/{key}/position/x', x_translation, extrapolation='constant', curve_order='linear', value_index=-1)
            contents = self.add_animation(node_name, contents, f'uv_track_vertices/{key}/position/y', y_translation, extrapolation='constant', curve_order='linear', value_index=-1)      

        # Write the modified setup list back to setup file

        with open(self.node_filename, 'w') as edit_node :
            for l in contents :
                edit_node.write(l)

        # Reload saved node

        self.reload_selected_node()

        # Remove temp folder

        self.remove_temp_folder()

        PyFlameFunctions.message_print(f'Surface UVs Loaded "{self.track_name}" loaded', SCRIPT_NAME)

    def key_frame(self, index, frame, value, value_lock=False, curve_order='linear') :
        # Creates a list of all setup lines to write out for a key frame based on supplied values

        kf_lines = [
            f'\t\t\tKey {index}\n',
            f'\t\t\t\tFrame {frame}\n',
            f'\t\t\t\tValue {value}\n',
            '\t\t\t\tRHandle_dX 0.25\n',
            '\t\t\t\tRHandle_dY 0\n',
            '\t\t\t\tLHandle_dX -0.25\n',
            '\t\t\t\tLHandle_dY 0\n',
            '\t\t\t\tCurveMode hermite\n',
            f'\t\t\t\tCurveOrder {curve_order}\n',
            '\t\t\t\tEnd\n'
        ]

        if value_lock : kf_lines.insert(7, '\t\t\t\tValueLock yes\n')

        return kf_lines
    
    def extract_dimension(self, corner, dimension):
        # Pulls out just x or y animation from a full corner list

        if dimension == 'x' :
            return [(p[0], p[1]) for p in corner]
        elif dimension == 'y' :
            return [(p[0], p[2]) for p in corner]

    def add_tracker(self, tracker, corner, width, height) :

        #Creates all lines for a tracker attachment (stabilizer setup)

        ref_frame = corner[0][0]

        attachment_lines = [
            '\tAttachement Tracker\n',
            f'\tAttachementName \t"{tracker}"\n',
            '\tActive yes\n',
            '\tFixedRef no\n',
            '\tFixedX no\n',
            '\tFixedY no\n',
            '\tTolerance 100\n',
            '\tColour\n',
            '\t\tRed 100\n',
            '\t\tGreen 0\n',
            '\t\tBlue 0\n',
            '\tOffsetsX 0\n',
            '\tOffsetsY 0\n',
            f'\tFirstRefFrame {ref_frame}\n',
            '\tAnim\n',
            'Channel ref/x\n',
            '\tExtrapolation constant\n',
            f'\tValue {corner[0][1]}\n',
            '\tSize 1\n',
            '\tKeyVersion 2\n'
        ]

        attachment_lines.extend([k[2:] for k in self.key_frame(0, ref_frame, corner[0][1])])

        # Creates x and y reference key frames on the start frame

        ref_y_lines = [
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel ref/y\n',
            '\tExtrapolation constant\n',
            f'\tValue {corner[0][2]}\n',
            '\tSize 1\n',
            '\tKeyVersion 2\n'
        ]

        attachment_lines.extend(ref_y_lines)
        attachment_lines.extend([k[2:] for k in self.key_frame(0, ref_frame, corner[0][2])])

        ref_lines = [
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel ref/width\n',
            '\tExtrapolation constant\n',
            '\tValue 64\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel ref/height\n',
            '\tExtrapolation constant\n',
            '\tValue 64\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel ref/dx\n',
            '\tExtrapolation constant\n',
            '\tValue 0\n',
            '\tSize 1\n',
            '\tKeyVersion 2\n'
        ]

        attachment_lines.extend(ref_lines)
        attachment_lines.extend([k[2:] for k in self.key_frame(0, ref_frame, 0)])
        
        ref_dy_lines = [
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel ref/dy\n',
            '\tExtrapolation constant\n',
            '\tValue 0\n',
            '\tSize 1\n',
            '\tKeyVersion 2\n'
        ]

        attachment_lines.extend(ref_dy_lines)
        attachment_lines.extend([k[2:] for k in self.key_frame(0, ref_frame, 0)])

        # Adds animation for shift channels as an offset from reference frame

        shift_x_lines = [
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel track/x\n',
            '\tExtrapolation linear\n',
            f'\tValue {width // 2}\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel track/y\n',
            '\tExtrapolation linear\n',
            f'\tValue {height // 2}\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel track/width\n',
            '\tExtrapolation constant\n',
            '\tValue 96\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel track/height\n',
            '\tExtrapolation constant\n',
            '\tValue 96\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel shift/x\n',
            '\tExtrapolation linear\n',
            '\tValue 0\n',
            f'\tSize {len(corner)}\n',
            '\tKeyVersion 2\n'
        ]

        attachment_lines.extend(shift_x_lines)

        for i, f in enumerate(corner) :         
            attachment_lines.extend([k[2:] for k in self.key_frame(i, f[0], corner[0][1] - f[1], curve_order='linear')])

        shift_y_lines = [
            '\tColour 255 0 0\n',
            '\tEnd\n',
            'Channel shift/y\n',
            '\tExtrapolation linear\n',
            '\tValue 0\n',
            f'\tSize {len(corner)}\n',
            '\tKeyVersion 2\n',
        ]

        attachment_lines.extend(shift_y_lines)

        for i, f in enumerate(corner) :

            attachment_lines.extend([k[2:] for k in self.key_frame(i, f[0], corner[0][2] - f[2], curve_order='linear')])

        attachment_end = [
            '\tColour 255 0 0\n',
            '\tEnd\n',
            'Channel offset/x\n',
            '\tExtrapolation linear\n',
            '\tValue 0\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'Channel offset/y\n',
            '\tExtrapolation linear\n',
            '\tValue 0\n',
            '\tColour 85 85 85\n',
            '\tEnd\n',
            'ChannelEnd\n',
            'AttachementEnd\n'
        ]
        attachment_lines.extend(attachment_end)

        return attachment_lines
        
    def add_animation(self, node_name, setup, channel, animation, value_lock=False, extrapolation='linear', curve_order='linear', value_index=0) :
        # Adds an animation curve to the passed channel in the setup list
        # node_name: name of the action/gmask tracer node to animate
        # setup: list of setup file contents by line
        # channel: string of the channel to animate ex. 'upper_left/position/x' etc
        # animation: list of keyframe tuples [(frame, value)...]
        #
        # returns full modified setup list

        node_line = self.find_line(node_name, setup)
        channel_line = self.find_line_after(channel, node_line, setup)

        setup[channel_line + 1] = f'\t\t\tExtrapolation {extrapolation}\n'
        setup[channel_line + 2] = f'\t\t\tValue {animation[value_index][1]}\n'

        animation_lines = [
            f'\t\t\tSize {len(animation)}\n',
            '\t\t\tKeyVersion 2\n']

        for anim_index, frame_value in enumerate(animation) :
            animation_lines.extend(self.key_frame(anim_index, frame_value[0], frame_value[1], value_lock, curve_order))

        for anim_line_index, animated_line_value in enumerate(animation_lines, channel_line + 3) :
            setup.insert(anim_line_index, animated_line_value)

        return setup
    
    def parse_mocha_files(self) :
        import re

        #creates browser to select .ascii mocha track files
        browser = PyFlameFunctions.file_browser(
            title = 'Select Four Mocha Tracker Files', 
            extension = ['ascii'],
            multi_selection = True,
            )
        
        selected_files = browser

        # throw exception if browser doesn't return 4 files
        if len(selected_files) != 4 :
            PyFlameFunctions.message_print('Exactly four tracker files must be selected.', SCRIPT_NAME)
            raise ValueError('Exactly four tracker files must be selected.')

        tracker_file_names = []

        for i in selected_files :
            l = i.split('/')
            filename = l[-1]

            tracker_file_names.append(filename)
        
        tracker_regex = re.compile('_Tracker[1-4]')     # Mocha track regular expression
        
        mocha_names = []

        # scan through list of filenames for problems

        for file in tracker_file_names :
            mocha_suffix = tracker_regex.search(file)

            if mocha_suffix == None :
                # throw an exception if it doesn't find our regular expression

                error_msg = f'This file doesn\'t look like a Mocha Track: {file}'

                PyFlameFunctions.message_print(error_msg, SCRIPT_NAME)
                raise TypeError(error_msg)
            
            else :
                name_end = mocha_suffix.start()
                tracker_name = file[:name_end]
                mocha_names.append(tracker_name)
                
                # throw an exception if files are from different tracks.
                # otherwise, set instance track name to the mocha track name

                if len(set(mocha_names)) != 1 :

                    name_error = f'Selected trackers have different names: {repr(set(mocha_names))}'

                    PyFlameFunctions.message_print(name_error, SCRIPT_NAME)
                    raise ValueError(name_error)
                else : 
                    self.track_name = mocha_names[0]

        # finally, add our corners to our instance's attributes
        
        def frame_to_tuple(file_line):
            #converts a line of mocha track data into a tuple: (frame num, x, y)

            stripped = ''.join(file_line.split())
            no_colon = stripped.replace(':', ',')
            line_info_slice = no_colon.split(',')

            frame_float = float(line_info_slice[0])
            frame_int = int(frame_float)

            frame_info = (frame_int + self.sf_offset, float(line_info_slice[1]), float(line_info_slice[2]))

            return frame_info
    
        for l in selected_files :

            with open(l, 'r') as f :
                for line in f :
                    track_frame = frame_to_tuple(line)

                    if l[0:-6].endswith('Tracker1') :
                        self.upper_left.append(track_frame)
                    elif l[0:-6].endswith('Tracker2') :
                        self.upper_right.append(track_frame)
                    elif l[0:-6].endswith('Tracker3') :
                        self.lower_left.append(track_frame)
                    elif l[0:-6].endswith('Tracker4') :
                        self.lower_right.append(track_frame)

        self.corners = {
            'lower_left': self.lower_left,
            'upper_left': self.upper_left,
            'lower_right': self.lower_right,
            'upper_right': self.upper_right
        }
    
    def find_line(self, item, setup):
        # Fetches the index of a passed string in a setup list
        # slightly modified version of a method of the same name from Michael Vaglienty's Invert Axis script. 

        for num, line in enumerate(setup):
            if item in line:
                item_line = num
                return item_line
        
    def find_line_after(self, item, item_line_num, setup):
        # Fetches the index of a string 'item' that appears after a passed index in setup list
        # slightly modified version of a method of the same name from Michael Vaglienty's Invert Axis script

        for num, line in enumerate(setup):
            if num > item_line_num:
                if item in line:
                    line_number = num
                    return line_number

    def name_import(self, name, object_num=0):
        # Checks to see if any nodes already have the same name as our Mocha track
        # based on the method name_axis() from Michael Vaglienty's Invert Axis script

        import flame

        existing_nodes = [node.name.get_value() for node in self.host_node.nodes]

        if name not in existing_nodes:
            return name
        
        object_num += 1

        return self.name_import(f'{self.track_name}{object_num}', object_num)
    
    # Following methods were all lifted from Michael Vaglienty's Invert Axis script

    def save_selected_node(self):
        import flame

        # Create temp save dir

        try:
            os.makedirs(self.temp_folder)
        except:
            shutil.rmtree(self.temp_folder)
            os.makedirs(self.temp_folder)

        # Save selected node

        self.host_node.save_node_setup(self.save_node_path)

    def reload_selected_node(self):

        # Reload node setup

        self.host_node.load_node_setup(self.save_node_path)

    def remove_temp_folder(self):

        # Remove temp folder

        shutil.rmtree(self.temp_folder)

def perspective_grid(self) :
    pg = MochaTrack()

    pg.import_perspective_grid()
    
def surface_uvs(self) :
    suv = MochaTrack()

    suv.import_bilinear_uvs()

#           Scope               #
# ----------------------------- #

def scope_action_background(selection) :
    
    return len(selection) == 0

#            Menu               #
# ----------------------------- #

def get_action_custom_ui_actions():

    return [
        {
            'name': 'Import Mocha Track',
            'actions': [
                {
                    'name': 'Perspective Grid',
                    'isVisible': scope_action_background,
                    'execute': perspective_grid,
                    'minimumVersion': '2022'
                },
                {
                    'name': 'Surface UVs',
                    'isVisible': scope_action_background,
                    'execute': surface_uvs,
                    'minimumVersion': '2022'
                }
            ]
        }
    ]