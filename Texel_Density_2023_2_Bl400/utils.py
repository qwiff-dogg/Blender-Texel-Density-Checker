import bpy
import bmesh
import math
import colorsys
from datetime import datetime
import os


# Value by range to Color gradient by hue
def Value_To_Color(value, range_min, range_max):
	# Remap value to range 0.0 - 1.0
	if range_min == range_max or abs(range_max - range_min) < 0.001:
		remapped_value = 0.5
	else:
		remapped_value = (value - range_min) / (range_max - range_min)
		remapped_value = Saturate(remapped_value)

	# Calculate hue and get color
	hue = (1 - remapped_value) * 0.67
	color = colorsys.hsv_to_rgb(hue, 1, 1)
	color4 = (color[0], color[1], color[2], 1)
	return color4

# Sync selection between UV Editor and 3D View
def Sync_UV_Selection():
	mesh = bpy.context.active_object.data
	bm = bmesh.from_edit_mesh(mesh)
	bm.faces.ensure_lookup_table()
	uv_layer = bm.loops.layers.uv.active
	uv_selected_faces = []
	face_count = len(bm.faces)

	# Add face to list if face select in UV Editor and in 3D View
	for face_id in range(face_count):
		face_is_selected = True
		for loop in bm.faces[face_id].loops:
			if not loop[uv_layer].select:
				face_is_selected = False
	
		if face_is_selected and bm.faces[face_id].select:
			uv_selected_faces.append(face_id)

	# Deselect all faces in UV Editor and select faces from list
	for face_id in range(face_count):
		for loop in bm.faces[face_id].loops:
			loop[uv_layer].select = False

	for face_id in uv_selected_faces:
		for loop in bm.faces[face_id].loops:
			loop[uv_layer].select = True

	# if set mode "Selected Faces" select faces from list
	for face in bm.faces:
		if bpy.context.scene.td.selected_faces:
			face.select_set(False)
		else:
			face.select_set(True)
		
	for face_id in uv_selected_faces:
		bm.faces[face_id].select_set(True)

	bmesh.update_edit_mesh(mesh)

# Get List of TD and UV area for each selected polygon
def Calculate_TD_Area_To_List():
	td = bpy.context.scene.td
	calculated_obj_td_area = []

	# Save current mode and active object
	start_active_obj = bpy.context.active_object
	start_mode = bpy.context.object.mode

	# Set default values
	area = 0
	gm_area = 0
	texture_size_cur_x = 1024
	texture_size_cur_y = 1024
	
	# Get texture size from panel
	if td.texture_size == '0':
		texture_size_cur_x = 512
		texture_size_cur_y = 512
	if td.texture_size == '1':
		texture_size_cur_x = 1024
		texture_size_cur_y = 1024
	if td.texture_size == '2':
		texture_size_cur_x = 2048
		texture_size_cur_y = 2048
	if td.texture_size == '3':
		texture_size_cur_x = 4096
		texture_size_cur_y = 4096
	if td.texture_size == '4':
		try:
			texture_size_cur_x = int(td.custom_width)
		except:
			texture_size_cur_x = 1024
		try:
			texture_size_cur_y = int(td.custom_height)
		except:
			texture_size_cur_y = 1024

	if texture_size_cur_x < 1 or texture_size_cur_y < 1:
		texture_size_cur_x = 1024
		texture_size_cur_y = 1024

	bpy.ops.object.mode_set(mode='OBJECT')

	face_count = len(bpy.context.active_object.data.polygons)

	# Duplicate and Triangulate Object
	bpy.ops.object.duplicate()
	bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
	bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

	aspect_ratio = texture_size_cur_x / texture_size_cur_y

	if aspect_ratio < 1:
		aspect_ratio = 1 / aspect_ratio
	largest_side = texture_size_cur_x if texture_size_cur_x > texture_size_cur_y else texture_size_cur_y

	# Get mesh data from active object
	bpy.ops.object.mode_set(mode='EDIT')
	bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
	bm.faces.ensure_lookup_table()
	
	for x in range(0, face_count):
		area = 0
		
		# Calculate total UV area
		loops = []
		for loop in bm.faces[x].loops:
			loops.append(loop[bm.loops.layers.uv.active].uv)
			
		loops_count = len(loops)
		a = loops_count - 1
		
		for b in range(0, loops_count):
			area += (loops[a].x + loops[b].x) * (loops[a].y - loops[b].y)
			a = b
		
		area = abs(0.5 * area)

		# Geometry Area
		gm_area = bpy.context.active_object.data.polygons[x].area

		# TexelDensity calculating from selected in panel texture size
		if gm_area > 0 and area > 0:
			texel_density = ((largest_side / math.sqrt(aspect_ratio)) * math.sqrt(area))/(math.sqrt(gm_area)*100) / bpy.context.scene.unit_settings.scale_length
		else:
			texel_density = 0.0001

		if td.units == '1':
			texel_density = texel_density*100
		if td.units == '2':
			texel_density = texel_density*2.54
		if td.units == '3':
			texel_density = texel_density*30.48

		td_area_list = [texel_density, area]
		calculated_obj_td_area.append(td_area_list)

	bpy.ops.object.mode_set(mode='OBJECT')

	# Save name of data for cleanup
	mesh_data_name = bpy.context.view_layer.objects.active.data.name

	# Delete duplicated object and mesh data
	bpy.ops.object.delete()
	try:
		bpy.data.meshes.remove(bpy.data.meshes[mesh_data_name])
	except:
		pass

	bpy.context.view_layer.objects.active = start_active_obj
	
	bpy.ops.object.mode_set(mode=start_mode)

	return calculated_obj_td_area

# Get list of islands (slow)
def Get_UV_Islands():
	start_selected_3d_faces = []
	start_selected_uv_faces = []
	start_hidden_faces = []
	start_mode = bpy.context.object.mode
	start_uv_sync_mode = bpy.context.scene.tool_settings.use_uv_select_sync

	bpy.ops.object.mode_set(mode='EDIT')

	bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
	bm.faces.ensure_lookup_table()
	uv_layer = bm.loops.layers.uv.active
	face_count = len(bm.faces)

	# Save start selected and hidden faces
	for face in bm.faces:
		if face.select:
			start_selected_3d_faces.append(face.index)
		if face.hide:
			start_hidden_faces.append(face.index)
		
		face_is_uv_selected = True
		for loop in face.loops:
			if not loop[uv_layer].select:
				face_is_uv_selected = False

		if face_is_uv_selected:
			start_selected_uv_faces.append(face.index)

	bpy.context.scene.tool_settings.use_uv_select_sync = False
	bpy.ops.mesh.reveal()
	bpy.ops.mesh.select_all(action='SELECT')

	face_dict = {}
	face_dict = [f for f in range(0, face_count)]
	uv_islands = []

	face_dict_len_start = len(face_dict)
	face_dict_len_finish = 0

	while len(face_dict) > 0:
		if face_dict_len_finish == face_dict_len_start:
			print("Can not Select Island")
			uv_islands = []
			break

		face_dict_len_start = len(face_dict)
		
		uv_island = []
		bpy.ops.uv.select_all(action='DESELECT')

		for loop in bm.faces[face_dict[0]].loops:
			loop[uv_layer].select = True

		bpy.ops.uv.select_linked()

		for face_id in range(face_count):
			face_is_selected = True
			for loop in bm.faces[face_id].loops:
				if not loop[uv_layer].select:
					face_is_selected = False

			if face_is_selected and bm.faces[face_id].select:
				uv_island.append(face_id)

		for face_id in uv_island:
			face_dict.remove(face_id)

		face_dict_len_finish = len(face_dict)

		bpy.ops.uv.select_all(action='DESELECT')

		uv_islands.append(uv_island)

	# Restore Saved Parameters
	bpy.ops.mesh.select_all(action='DESELECT')
	bpy.context.scene.tool_settings.use_uv_select_sync = start_uv_sync_mode
	bpy.ops.uv.select_all(action='DESELECT')

	for face_id in start_selected_3d_faces:
		bm.faces[face_id].select = True

	for face_id in start_selected_uv_faces:
		for loop in bm.faces[face_id].loops:
			loop[uv_layer].select = True

	for face_id in start_hidden_faces:
		bm.faces[face_id].hide_set(True)

	bmesh.update_edit_mesh(bpy.context.active_object.data)

	bpy.ops.object.mode_set(mode=start_mode)

	return uv_islands

# Example for use get_selected_islands()

#data = bpy.context.active_object.data
#bm = bmesh.from_edit_mesh(data)
#uv_layers = bm.loops.layers.uv.verify()
#islands = get_selected_islands(bm, uv_layers)

# Get list of islands (fast)
def get_selected_islands(bm, uv_layers):
    islands = []
    island = []
    
    sync = bpy.context.scene.tool_settings.use_uv_select_sync
    
    faces = bm.faces
    # Reset tags for unselected (if tag is False - skip)
    if sync is False:
        for face in faces:
            face.tag = all(l[uv_layers].select for l in face.loops)
    else:
        for face in faces:
            face.tag = face.select

    for face in faces:
        # Skip unselected and appended faces
        if face.tag is False:
            continue
        
        # Tag first element in island (for dont add again)
        face.tag = False
        
        # Container collector of island elements
        parts_of_island = [face]
        
        # Conteiner for get elements from loop from parts_of_island
        temp=[]
        
        # Blank list == all faces of the island taken
        while parts_of_island:
            for f in parts_of_island:
                # Running through all the neighboring faces
                for l in f.loops:                
                    link_face = l.link_loop_radial_next.face
                    # Skip appended
                    if link_face.tag is False:
                        continue
                    
                    for ll in link_face.loops:
                        if ll.face.tag is False:
                            continue
                        # If the coordinates of the vertices of adjacent 
                        # faces on the uv match, then this is part of the
                        # island and we append face to the list
                        co = l[uv_layers].uv
                        if ll[uv_layers].uv == co:
                            temp.append(ll.face)
                            ll.face.tag = False
                            
            island.extend(parts_of_island)
            parts_of_island = temp      
            temp = []
        islands.append(island)
        island = []
    return islands


def Saturate(val):
	return max(min(val, 1), 0)

#Get BlenderVersion
def Get_Version():
	result = 0
	version = bpy.app.version_string[:4]
	if version[-1:] == ".":
		version = version[:3]
	try:
		result = float(version)
	except:
		result = 2.90
	
	return result

# Execution Time
def Print_Execution_Time(function_name, start_time):
	td = bpy.context.scene.td

	if td.debug:
		finish_time = datetime.now()
		execution_time = finish_time - start_time
		seconds = (execution_time.total_seconds())
		milliseconds = round(seconds * 1000)
		print(function_name + " finished in " + str(seconds) + "s (" + str(milliseconds) + "ms)")


def Get_Addon_Name():
	return os.path.basename(os.path.dirname(os.path.realpath(__file__)))

def Get_Preferences():
	preferences = bpy.context.preferences
	addon_prefs = preferences.addons[__package__].preferences

	return addon_prefs
	# return bpy.context.preferences.addons[Get_Addon_Name()].preferences
