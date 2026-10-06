import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
import bpy, bmesh, json, math, mathutils
_coll_name = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
if _coll_name not in bpy.data.collections:
    _c = bpy.data.collections.new(_coll_name)
    bpy.context.scene.collection.children.link(_c)
_coll = bpy.data.collections.get(_coll_name)
def _link(obj):
    if _coll: _coll.objects.link(obj)
    else: bpy.context.scene.collection.objects.link(obj)
def _unlink_all(obj):
    for c in list(obj.users_collection): c.objects.unlink(obj)
_sentinel_results = {}
if 'arm_back_cylinder_f8c5c3' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.12, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'arm_back_cylinder_f8c5c3'; _obj.data.name = 'arm_back_cylinder_f8c5c3'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 0.119], [-1.0, 0.0, 6.123233995736766e-17, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_back_cylinder_f8c5c3'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_back_cylinder_f8c5c3')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_back_cylinder_f8c5c3')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_back_cylinder_28'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_arm_back_cylinder_28'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_back_cylinder_f8c5c3')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_back_cylinder_f8c5c3')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_back_cylinder_f8c5c3')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_front_cylinder_b7d100' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.12, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'arm_front_cylinder_b7d100'; _obj.data.name = 'arm_front_cylinder_b7d100'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, -0.119], [-1.0, 0.0, 6.123233995736766e-17, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_front_cylinder_b7d100'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_front_cylinder_b7d100')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_front_cylinder_b7d100')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_front_cylinder_21'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_arm_front_cylinder_21'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_front_cylinder_b7d100')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_front_cylinder_b7d100')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_front_cylinder_b7d100')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_left_cylinder_d9531f' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.12, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'arm_left_cylinder_d9531f'; _obj.data.name = 'arm_left_cylinder_d9531f'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, 1.0, -0.185], [0.0, 1.0, 0.0, 0.0], [-1.0, 0.0, 6.123233995736766e-17, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_left_cylinder_d9531f'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_left_cylinder_d9531f')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_left_cylinder_d9531f')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_left_cylinder_35'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_arm_left_cylinder_35'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_left_cylinder_d9531f')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_left_cylinder_d9531f')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_left_cylinder_d9531f')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_right_cylinder_9e0196' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.12, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'arm_right_cylinder_9e0196'; _obj.data.name = 'arm_right_cylinder_9e0196'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, 1.0, 0.185], [0.0, 1.0, 0.0, 0.0], [-1.0, 0.0, 6.123233995736766e-17, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_right_cylinder_9e0196'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_right_cylinder_9e0196')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_right_cylinder_9e0196')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_right_cylinder_42'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_arm_right_cylinder_42'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_right_cylinder_9e0196')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_right_cylinder_9e0196')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_right_cylinder_9e0196')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_assembly_root_9ca86d' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.14, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'arm_assembly_root_9ca86d'; _obj.data.name = 'arm_assembly_root_9ca86d'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, 1.0, 0.265], [0.0, 1.0, 0.0, -0.1525], [-1.0, 0.0, 6.123233995736766e-17, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_assembly_root_9ca86d'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_assembly_root_9ca86d')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_assembly_root_9ca86d')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_assembly_root_49'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_assembly_root_49'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_assembly_root_9ca86d')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.003, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_assembly_root_9ca86d')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_assembly_root_9ca86d')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'chassis_base_3d1a2c' not in bpy.data.objects:
    _mesh = bpy.data.meshes.new('chassis_base_3d1a2c')
    _bm = bmesh.new()
    bmesh.ops.create_cube(_bm, size=1.0)
    for _v in _bm.verts: _v.co.x*=0.25; _v.co.y*=0.18; _v.co.z*=0.04
    _bm.to_mesh(_mesh); _bm.free()
    _obj = bpy.data.objects.new('chassis_base_3d1a2c', _mesh)
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _link(_obj)
    _sentinel_results['chassis_base_3d1a2c'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('chassis_base_3d1a2c')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: chassis_base_3d1a2c')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_chassis_base_9'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_chassis_base_9'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('chassis_base_3d1a2c')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('chassis_base_3d1a2c')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('chassis_base_3d1a2c')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_bcb67fd73dbe_9cbba46fa2') or bpy.data.materials.new('MatPBR_bcb67fd73dbe_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.00440084974745434, 0.004896310081623859, 0.00598105957261676, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'u_shape_bracket_25de42' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.04,minor_radius=0.012,major_segments=48,minor_segments=16,location=(0,0,0),rotation=(0,0,0))
    _obj = bpy.context.active_object
    _obj.name = 'u_shape_bracket_25de42'; _obj.data.name = 'u_shape_bracket_25de42'
    _bm3=bmesh.new(); _bm3.from_mesh(_obj.data)
    _g3=_bm3.verts[:]+_bm3.edges[:]+_bm3.faces[:]
    bmesh.ops.bisect_plane(_bm3,geom=_g3,plane_co=(0,0,0),plane_no=(1,0,0),clear_inner=True,clear_outer=False)
    bmesh.ops.remove_doubles(_bm3,verts=_bm3.verts,dist=0.0001)
    _bnd3=[e for e in _bm3.edges if len(e.link_faces)==1]
    if _bnd3: bmesh.ops.edgeloop_fill(_bm3,edges=_bnd3)
    _rz=mathutils.Matrix.Rotation(math.pi/2,4,'Z'); _rx=mathutils.Matrix.Rotation(math.pi/2,4,'X')
    bmesh.ops.transform(_bm3,matrix=_rx@_rz,verts=_bm3.verts)
    _mz3=min(v.co.z for v in _bm3.verts)
    bmesh.ops.translate(_bm3,vec=mathutils.Vector((0,0,-_mz3)),verts=_bm3.verts)
    _bm3.to_mesh(_obj.data); _bm3.free(); _obj.data.update()
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.16599999999999998], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['u_shape_bracket_25de42'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('u_shape_bracket_25de42')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: u_shape_bracket_25de42')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_u_shape_bracket_61'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_bracket_assembly_4/m_f4b618e2bc_u_shape_bracket_61'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('u_shape_bracket_25de42')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('u_shape_bracket_25de42')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('u_shape_bracket_25de42')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'camera_lens_ed4799' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.02)
    _obj = bpy.context.active_object
    _obj.name = 'camera_lens_ed4799'; _obj.data.name = 'camera_lens_ed4799'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.0019999999999999983], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['camera_lens_ed4799'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('camera_lens_ed4799')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: camera_lens_ed4799')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_camera_lens_16'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_camera_lens_16'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('camera_lens_ed4799')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('camera_lens_ed4799')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('camera_lens_ed4799')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_04e2bc59e2a9_9cbba46fa2') or bpy.data.materials.new('MatPBR_04e2bc59e2a9_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 0.1)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.0
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 0.1
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.85
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.85
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.85 > 0 or 0.1 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'camera_lens_holder_9bfccb' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'camera_lens_holder_9bfccb'; _obj.data.name = 'camera_lens_holder_9bfccb'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.141], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['camera_lens_holder_9bfccb'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('camera_lens_holder_9bfccb')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: camera_lens_holder_9bfccb')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_camera_lens_holder_62'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_bracket_assembly_4/m_f4b618e2bc_camera_lens_holder_62'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('camera_lens_holder_9bfccb')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('camera_lens_holder_9bfccb')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('camera_lens_holder_9bfccb')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_04e2bc59e2a9_9cbba46fa2') or bpy.data.materials.new('MatPBR_04e2bc59e2a9_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 0.1)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.0
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 0.1
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.85
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.85
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.85 > 0 or 0.1 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'landing_feet_front_left_35fddc' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.04, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'landing_feet_front_left_35fddc'; _obj.data.name = 'landing_feet_front_left_35fddc'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.12], [0.0, 1.0, 0.0, -0.09], [0.0, 0.0, 1.0, -0.06], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['landing_feet_front_left_35fddc'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('landing_feet_front_left_35fddc')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: landing_feet_front_left_35fddc')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_landing_feet_front_left_63'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_landing_feet_8/m_f4b618e2bc_landing_feet_front_left_63'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_cl_obj = bpy.data.objects.get('landing_feet_front_left_35fddc')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('landing_feet_front_left_35fddc')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_0a86e394142e_9cbba46fa2') or bpy.data.materials.new('MatPBR_0a86e394142e_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'landing_feet_front_right_28d011' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.04, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'landing_feet_front_right_28d011'; _obj.data.name = 'landing_feet_front_right_28d011'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.12], [0.0, 1.0, 0.0, -0.09], [0.0, 0.0, 1.0, -0.06], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['landing_feet_front_right_28d011'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('landing_feet_front_right_28d011')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: landing_feet_front_right_28d011')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_landing_feet_front_right_64'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_landing_feet_8/m_f4b618e2bc_landing_feet_front_right_64'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_cl_obj = bpy.data.objects.get('landing_feet_front_right_28d011')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('landing_feet_front_right_28d011')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_0a86e394142e_9cbba46fa2') or bpy.data.materials.new('MatPBR_0a86e394142e_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'landing_feet_rear_left_32eb7d' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.04, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'landing_feet_rear_left_32eb7d'; _obj.data.name = 'landing_feet_rear_left_32eb7d'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.12], [0.0, 1.0, 0.0, 0.09], [0.0, 0.0, 1.0, -0.06], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['landing_feet_rear_left_32eb7d'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('landing_feet_rear_left_32eb7d')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: landing_feet_rear_left_32eb7d')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_landing_feet_rear_left_65'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_landing_feet_8/m_f4b618e2bc_landing_feet_rear_left_65'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_cl_obj = bpy.data.objects.get('landing_feet_rear_left_32eb7d')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('landing_feet_rear_left_32eb7d')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_0a86e394142e_9cbba46fa2') or bpy.data.materials.new('MatPBR_0a86e394142e_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'landing_feet_rear_right_c0613e' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.04, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'landing_feet_rear_right_c0613e'; _obj.data.name = 'landing_feet_rear_right_c0613e'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.12], [0.0, 1.0, 0.0, 0.09], [0.0, 0.0, 1.0, -0.06], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['landing_feet_rear_right_c0613e'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('landing_feet_rear_right_c0613e')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: landing_feet_rear_right_c0613e')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_landing_feet_rear_right_66'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_landing_feet_8/m_f4b618e2bc_landing_feet_rear_right_66'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_cl_obj = bpy.data.objects.get('landing_feet_rear_right_c0613e')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('landing_feet_rear_right_c0613e')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_0a86e394142e_9cbba46fa2') or bpy.data.materials.new('MatPBR_0a86e394142e_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'sensor_barrel__sembly_1_09_9011fe' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.06, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'sensor_barrel__sembly_1_09_9011fe'; _obj.data.name = 'sensor_barrel__sembly_1_09_9011fe'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.011999999999999997], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['sensor_barrel__sembly_1_09_9011fe'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('sensor_barrel__sembly_1_09_9011fe')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: sensor_barrel__sembly_1_09_9011fe')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_sensor_barrel__sembly_1_09_17'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_sensor_barrel__sembly_1_09_17'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('sensor_barrel__sembly_1_09_9011fe')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('sensor_barrel__sembly_1_09_9011fe')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('sensor_barrel__sembly_1_09_9011fe')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_b6e342481af2_9cbba46fa2') or bpy.data.materials.new('MatPBR_b6e342481af2_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'sensor_lens_719dca' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.02)
    _obj = bpy.context.active_object
    _obj.name = 'sensor_lens_719dca'; _obj.data.name = 'sensor_lens_719dca'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.0019999999999999983], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['sensor_lens_719dca'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('sensor_lens_719dca')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: sensor_lens_719dca')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_sensor_lens_18'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_sensor_lens_18'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('sensor_lens_719dca')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('sensor_lens_719dca')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('sensor_lens_719dca')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_04e2bc59e2a9_9cbba46fa2') or bpy.data.materials.new('MatPBR_04e2bc59e2a9_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 0.1)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.0
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 0.1
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.85
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.85
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.85 > 0 or 0.1 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'camera_module_2e36d8' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.02)
    _obj = bpy.context.active_object
    _obj.name = 'camera_module_2e36d8'; _obj.data.name = 'camera_module_2e36d8'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.005000000000000001], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['camera_module_2e36d8'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('camera_module_2e36d8')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: camera_module_2e36d8')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_camera_module_5'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_camera_module_5'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('camera_module_2e36d8')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('camera_module_2e36d8')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('camera_module_2e36d8')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_1707af06c991_9cbba46fa2') or bpy.data.materials.new('MatPBR_1707af06c991_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if [0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0] and 3.0 > 0:
            _em = tuple([0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0])
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 3.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'sensor_barrel_92e6c0' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.04, vertices=32)
    _obj = bpy.context.active_object
    _obj.name = 'sensor_barrel_92e6c0'; _obj.data.name = 'sensor_barrel_92e6c0'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.0019999999999999983], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['sensor_barrel_92e6c0'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('sensor_barrel_92e6c0')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: sensor_barrel_92e6c0')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_sensor_barrel_6'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_sensor_barrel_6'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('sensor_barrel_92e6c0')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('sensor_barrel_92e6c0')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('sensor_barrel_92e6c0')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_b6e342481af2_9cbba46fa2') or bpy.data.materials.new('MatPBR_b6e342481af2_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')

# --- PIPELINE FLUSH CHUNK ---
import bpy, bmesh, json, math, mathutils
_coll_name = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
if _coll_name not in bpy.data.collections:
    _c = bpy.data.collections.new(_coll_name)
    bpy.context.scene.collection.children.link(_c)
_coll = bpy.data.collections.get(_coll_name)
def _link(obj):
    if _coll: _coll.objects.link(obj)
    else: bpy.context.scene.collection.objects.link(obj)
def _unlink_all(obj):
    for c in list(obj.users_collection): c.objects.unlink(obj)
_sentinel_results = {}
if 'collar_back_da3663' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'collar_back_da3663'; _obj.data.name = 'collar_back_da3663'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.119], [0.0, 0.0, 1.0, 0.017], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['collar_back_da3663'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('collar_back_da3663')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: collar_back_da3663')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_collar_back_29'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_collar_back_29'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('collar_back_da3663')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('collar_back_da3663')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('collar_back_da3663')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'collar_front_391248' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'collar_front_391248'; _obj.data.name = 'collar_front_391248'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, -0.119], [0.0, 0.0, 1.0, 0.017], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['collar_front_391248'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('collar_front_391248')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: collar_front_391248')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_collar_front_22'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_collar_front_22'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('collar_front_391248')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('collar_front_391248')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('collar_front_391248')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'collar_left_d2c7d8' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'collar_left_d2c7d8'; _obj.data.name = 'collar_left_d2c7d8'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.017], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['collar_left_d2c7d8'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('collar_left_d2c7d8')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: collar_left_d2c7d8')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_collar_left_36'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_collar_left_36'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('collar_left_d2c7d8')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('collar_left_d2c7d8')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('collar_left_d2c7d8')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'collar_right_62df8a' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'collar_right_62df8a'; _obj.data.name = 'collar_right_62df8a'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.017], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['collar_right_62df8a'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('collar_right_62df8a')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: collar_right_62df8a')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_collar_right_43'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_collar_right_43'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('collar_right_62df8a')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('collar_right_62df8a')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('collar_right_62df8a')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'guard_back_b4707c' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.025, minor_radius=0.004)
    _obj = bpy.context.active_object
    _obj.name = 'guard_back_b4707c'; _obj.data.name = 'guard_back_b4707c'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.119], [0.0, 0.0, 1.0, 0.023000000000000003], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['guard_back_b4707c'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('guard_back_b4707c')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: guard_back_b4707c')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_guard_back_30'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_guard_back_30'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('guard_back_b4707c')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('guard_back_b4707c')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('guard_back_b4707c')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'guard_front_6326a4' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.025, minor_radius=0.004)
    _obj = bpy.context.active_object
    _obj.name = 'guard_front_6326a4'; _obj.data.name = 'guard_front_6326a4'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, -0.119], [0.0, 0.0, 1.0, 0.023000000000000003], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['guard_front_6326a4'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('guard_front_6326a4')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: guard_front_6326a4')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_guard_front_23'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_guard_front_23'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('guard_front_6326a4')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('guard_front_6326a4')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('guard_front_6326a4')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'guard_left_64b0fa' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.025, minor_radius=0.004)
    _obj = bpy.context.active_object
    _obj.name = 'guard_left_64b0fa'; _obj.data.name = 'guard_left_64b0fa'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023000000000000003], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['guard_left_64b0fa'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('guard_left_64b0fa')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: guard_left_64b0fa')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_guard_left_37'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_guard_left_37'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('guard_left_64b0fa')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('guard_left_64b0fa')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('guard_left_64b0fa')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'guard_right_a4d51a' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.025, minor_radius=0.004)
    _obj = bpy.context.active_object
    _obj.name = 'guard_right_a4d51a'; _obj.data.name = 'guard_right_a4d51a'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023000000000000003], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['guard_right_a4d51a'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('guard_right_a4d51a')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: guard_right_a4d51a')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_guard_right_44'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_guard_right_44'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('guard_right_a4d51a')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('guard_right_a4d51a')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('guard_right_a4d51a')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'hub_back_00a00b' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01)
    _obj = bpy.context.active_object
    _obj.name = 'hub_back_00a00b'; _obj.data.name = 'hub_back_00a00b'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.119], [0.0, 0.0, 1.0, 0.037000000000000005], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['hub_back_00a00b'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('hub_back_00a00b')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: hub_back_00a00b')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_hub_back_31'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_hub_back_31'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('hub_back_00a00b')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('hub_back_00a00b')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('hub_back_00a00b')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'hub_front_525e50' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01)
    _obj = bpy.context.active_object
    _obj.name = 'hub_front_525e50'; _obj.data.name = 'hub_front_525e50'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, -0.119], [0.0, 0.0, 1.0, 0.037000000000000005], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['hub_front_525e50'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('hub_front_525e50')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: hub_front_525e50')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_hub_front_24'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_hub_front_24'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('hub_front_525e50')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('hub_front_525e50')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('hub_front_525e50')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'hub_left_8f2c8a' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01)
    _obj = bpy.context.active_object
    _obj.name = 'hub_left_8f2c8a'; _obj.data.name = 'hub_left_8f2c8a'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.037000000000000005], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['hub_left_8f2c8a'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('hub_left_8f2c8a')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: hub_left_8f2c8a')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_hub_left_38'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_hub_left_38'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('hub_left_8f2c8a')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('hub_left_8f2c8a')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('hub_left_8f2c8a')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'hub_right_4f33e2' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01)
    _obj = bpy.context.active_object
    _obj.name = 'hub_right_4f33e2'; _obj.data.name = 'hub_right_4f33e2'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.037000000000000005], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['hub_right_4f33e2'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('hub_right_4f33e2')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: hub_right_4f33e2')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_hub_right_45'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_hub_right_45'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('hub_right_4f33e2')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('hub_right_4f33e2')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('hub_right_4f33e2')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_back_1_1084ab' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.04)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_back_1_1084ab'; _obj.data.name = 'propeller_blade_back_1_1084ab'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.119], [0.0, 0.0, 1.0, 0.067], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_back_1_1084ab'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_back_1_1084ab')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_back_1_1084ab')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_back_1_32'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_propeller_blade_back_1_32'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_back_1_1084ab')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_back_1_1084ab')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_back_1_1084ab')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_front_1_ef209d' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.04)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_front_1_ef209d'; _obj.data.name = 'propeller_blade_front_1_ef209d'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, -0.119], [0.0, 0.0, 1.0, 0.067], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_front_1_ef209d'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_front_1_ef209d')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_front_1_ef209d')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_front_1_25'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_propeller_blade_front_1_25'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_front_1_ef209d')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_front_1_ef209d')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_front_1_ef209d')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_left_1_3fca5e' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_left_1_3fca5e'; _obj.data.name = 'propeller_blade_left_1_3fca5e'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.05950000000000001], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_left_1_3fca5e'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_left_1_3fca5e')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_left_1_3fca5e')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_left_1_39'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_propeller_blade_left_1_39'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_left_1_3fca5e')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_left_1_3fca5e')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_left_1_3fca5e')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_right_1_cbccc4' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_right_1_cbccc4'; _obj.data.name = 'propeller_blade_right_1_cbccc4'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.05950000000000001], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_right_1_cbccc4'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_right_1_cbccc4')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_right_1_cbccc4')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_right_1_46'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_propeller_blade_right_1_46'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_right_1_cbccc4')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_right_1_cbccc4')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_right_1_cbccc4')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_inner_collar_1_8dbfbe' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'arm_inner_collar_1_8dbfbe'; _obj.data.name = 'arm_inner_collar_1_8dbfbe'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.183], [0.0, 1.0, 0.0, -0.1525], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_inner_collar_1_8dbfbe'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_inner_collar_1_8dbfbe')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_inner_collar_1_8dbfbe')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_inner_collar_1_50'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_inner_collar_1_50'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_inner_collar_1_8dbfbe')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_inner_collar_1_8dbfbe')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_inner_collar_1_8dbfbe')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_inner_collar_2_771e3b' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'arm_inner_collar_2_771e3b'; _obj.data.name = 'arm_inner_collar_2_771e3b'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.34700000000000003], [0.0, 1.0, 0.0, -0.1845], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_inner_collar_2_771e3b'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_inner_collar_2_771e3b')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_inner_collar_2_771e3b')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_inner_collar_2_51'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_inner_collar_2_51'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_inner_collar_2_771e3b')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_inner_collar_2_771e3b')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_inner_collar_2_771e3b')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_inner_collar_3_6ed7ec' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'arm_inner_collar_3_6ed7ec'; _obj.data.name = 'arm_inner_collar_3_6ed7ec'
    _obj.matrix_world = mathutils.Matrix([[0.7071067811865476, 0.0, -0.7071067811865476, 0.3229827560572969], [0.0, 1.0, 0.0, -0.1845], [0.7071067811865476, 0.0, 0.7071067811865476, 0.05798275605729691], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_inner_collar_3_6ed7ec'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_inner_collar_3_6ed7ec')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_inner_collar_3_6ed7ec')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_inner_collar_3_52'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_inner_collar_3_52'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_inner_collar_3_6ed7ec')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_inner_collar_3_6ed7ec')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_inner_collar_3_6ed7ec')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_inner_collar_4_e77c4f' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'arm_inner_collar_4_e77c4f'; _obj.data.name = 'arm_inner_collar_4_e77c4f'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 0.0, -1.0, 0.265], [0.0, 1.0, 0.0, -0.1845], [1.0, 0.0, 6.123233995736766e-17, 0.082], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_inner_collar_4_e77c4f'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_inner_collar_4_e77c4f')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_inner_collar_4_e77c4f')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_inner_collar_4_53'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_inner_collar_4_53'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_inner_collar_4_e77c4f')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_inner_collar_4_e77c4f')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_inner_collar_4_e77c4f')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'arm_inner_collar_5_d8bbc2' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.01, minor_radius=0.002)
    _obj = bpy.context.active_object
    _obj.name = 'arm_inner_collar_5_d8bbc2'; _obj.data.name = 'arm_inner_collar_5_d8bbc2'
    _obj.matrix_world = mathutils.Matrix([[-0.7071067811865475, 0.0, -0.7071067811865476, 0.20701724394270313], [0.0, 1.0, 0.0, -0.1845], [0.7071067811865476, 0.0, -0.7071067811865475, 0.05798275605729691], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['arm_inner_collar_5_d8bbc2'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('arm_inner_collar_5_d8bbc2')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: arm_inner_collar_5_d8bbc2')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_arm_inner_collar_5_54'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_arm_inner_collar_5_54'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('arm_inner_collar_5_d8bbc2')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('arm_inner_collar_5_d8bbc2')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('arm_inner_collar_5_d8bbc2')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'battery_module__sembly_1_11_570249' not in bpy.data.objects:
    _mesh = bpy.data.meshes.new('battery_module__sembly_1_11_570249')
    _bm = bmesh.new()
    bmesh.ops.create_cube(_bm, size=1.0)
    for _v in _bm.verts: _v.co.x*=0.04; _v.co.y*=0.03; _v.co.z*=0.02
    _bm.to_mesh(_mesh); _bm.free()
    _obj = bpy.data.objects.new('battery_module__sembly_1_11_570249', _mesh)
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.105], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _link(_obj)
    _sentinel_results['battery_module__sembly_1_11_570249'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('battery_module__sembly_1_11_570249')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: battery_module__sembly_1_11_570249')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_battery_module__sembly_1_11_19'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_battery_module__sembly_1_11_19'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('battery_module__sembly_1_11_570249')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('battery_module__sembly_1_11_570249')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('battery_module__sembly_1_11_570249')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_5bc5ac73d158_9cbba46fa2') or bpy.data.materials.new('MatPBR_5bc5ac73d158_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if [0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0] and 3.0 > 0:
            _em = tuple([0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0])
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 3.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'led_1_0d4589' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'led_1_0d4589'; _obj.data.name = 'led_1_0d4589'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.025], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['led_1_0d4589'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('led_1_0d4589')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: led_1_0d4589')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_led_1_20'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_led_1_20'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('led_1_0d4589')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('led_1_0d4589')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('led_1_0d4589')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_1707af06c991_9cbba46fa2') or bpy.data.materials.new('MatPBR_1707af06c991_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if [0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0] and 3.0 > 0:
            _em = tuple([0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0])
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 3.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_guard_1_d5f942' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_guard_1_d5f942'; _obj.data.name = 'rotor_guard_1_d5f942'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.394], [0.0, 1.0, 0.0, -0.1525], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_guard_1_d5f942'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_guard_1_d5f942')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_guard_1_d5f942')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_guard_1_55'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_guard_1_55'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_guard_1_d5f942')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_guard_1_d5f942')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_guard_1_d5f942')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_guard_2_54b27b' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_guard_2_54b27b'; _obj.data.name = 'rotor_guard_2_54b27b'
    _obj.matrix_world = mathutils.Matrix([[-1.0, 0.0, -1.2246467991473532e-16, 0.16], [0.0, 1.0, 0.0, -0.2075], [1.2246467991473532e-16, 0.0, -1.0, 1.285879139104721e-17], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_guard_2_54b27b'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_guard_2_54b27b')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_guard_2_54b27b')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_guard_2_56'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_guard_2_56'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_guard_2_54b27b')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_guard_2_54b27b')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_guard_2_54b27b')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_guard_3_cda35f' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_guard_3_cda35f'; _obj.data.name = 'rotor_guard_3_cda35f'
    _obj.matrix_world = mathutils.Matrix([[-0.7071067811865477, 0.0, 0.7071067811865475, 0.19075378797541248], [0.0, 1.0, 0.0, -0.2075], [-0.7071067811865475, 0.0, -0.7071067811865477, -0.07424621202458749], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_guard_3_cda35f'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_guard_3_cda35f')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_guard_3_cda35f')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_guard_3_57'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_guard_3_57'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_guard_3_cda35f')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_guard_3_cda35f')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_guard_3_cda35f')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_guard_4_daa403' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_guard_4_daa403'; _obj.data.name = 'rotor_guard_4_daa403'
    _obj.matrix_world = mathutils.Matrix([[-1.8369701987210297e-16, 0.0, 1.0, 0.265], [0.0, 1.0, 0.0, -0.2075], [-1.0, 0.0, -1.8369701987210297e-16, -0.10500000000000001], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_guard_4_daa403'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_guard_4_daa403')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_guard_4_daa403')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_guard_4_58'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_guard_4_58'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_guard_4_daa403')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_guard_4_daa403')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_guard_4_daa403')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_guard_5_206789' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.005)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_guard_5_206789'; _obj.data.name = 'rotor_guard_5_206789'
    _obj.matrix_world = mathutils.Matrix([[0.7071067811865474, 0.0, 0.7071067811865477, 0.3392462120245875], [0.0, 1.0, 0.0, -0.2075], [-0.7071067811865477, 0.0, 0.7071067811865474, -0.07424621202458752], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_guard_5_206789'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_guard_5_206789')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_guard_5_206789')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_guard_5_59'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_guard_5_59'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_guard_5_206789')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_guard_5_206789')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_guard_5_206789')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'rotor_hub_1_fa740e' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012)
    _obj = bpy.context.active_object
    _obj.name = 'rotor_hub_1_fa740e'; _obj.data.name = 'rotor_hub_1_fa740e'
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.265], [0.0, 1.0, 0.0, -0.1845], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['rotor_hub_1_fa740e'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('rotor_hub_1_fa740e')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: rotor_hub_1_fa740e')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_rotor_hub_1_60'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_arm_assembly_3/m_f4b618e2bc_rotor_hub_1_60'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('rotor_hub_1_fa740e')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('rotor_hub_1_fa740e')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('rotor_hub_1_fa740e')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_cc6677337ee8_9cbba46fa2') or bpy.data.materials.new('MatPBR_cc6677337ee8_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.25
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.58
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'status_dome__sembly_1_02_c66f18' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03)
    _obj = bpy.context.active_object
    _obj.name = 'status_dome__sembly_1_02_c66f18'; _obj.data.name = 'status_dome__sembly_1_02_c66f18'
    _bm2 = bmesh.new(); _bm2.from_mesh(_obj.data)
    _geom2 = _bm2.verts[:]+_bm2.edges[:]+_bm2.faces[:]
    bmesh.ops.bisect_plane(_bm2,geom=_geom2,plane_co=(0,0,0),plane_no=(0,0,1),clear_inner=True,clear_outer=False)
    bmesh.ops.remove_doubles(_bm2,verts=_bm2.verts,dist=0.0001)
    _bnd=[e for e in _bm2.edges if len(e.link_faces)==1]
    if _bnd: bmesh.ops.edgeloop_fill(_bm2,edges=_bnd)
    _bm2.to_mesh(_obj.data); _bm2.free()
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.030000000000000002], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['status_dome__sembly_1_02_c66f18'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('status_dome__sembly_1_02_c66f18')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: status_dome__sembly_1_02_c66f18')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_status_dome__sembly_1_02_10'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_status_dome__sembly_1_02_10'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('status_dome__sembly_1_02_c66f18')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('status_dome__sembly_1_02_c66f18')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('status_dome__sembly_1_02_c66f18')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_c80665234ee2_9cbba46fa2') or bpy.data.materials.new('MatPBR_c80665234ee2_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 0.05)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.0
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 0.05
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 1.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 1.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (1.0 > 0 or 0.05 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'u_bracket_27be47' not in bpy.data.objects:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.06,minor_radius=0.012,major_segments=48,minor_segments=16,location=(0,0,0),rotation=(0,0,0))
    _obj = bpy.context.active_object
    _obj.name = 'u_bracket_27be47'; _obj.data.name = 'u_bracket_27be47'
    _bm3=bmesh.new(); _bm3.from_mesh(_obj.data)
    _g3=_bm3.verts[:]+_bm3.edges[:]+_bm3.faces[:]
    bmesh.ops.bisect_plane(_bm3,geom=_g3,plane_co=(0,0,0),plane_no=(1,0,0),clear_inner=True,clear_outer=False)
    bmesh.ops.remove_doubles(_bm3,verts=_bm3.verts,dist=0.0001)
    _bnd3=[e for e in _bm3.edges if len(e.link_faces)==1]
    if _bnd3: bmesh.ops.edgeloop_fill(_bm3,edges=_bnd3)
    _rz=mathutils.Matrix.Rotation(math.pi/2,4,'Z'); _rx=mathutils.Matrix.Rotation(math.pi/2,4,'X')
    bmesh.ops.transform(_bm3,matrix=_rx@_rz,verts=_bm3.verts)
    _mz3=min(v.co.z for v in _bm3.verts)
    bmesh.ops.translate(_bm3,vec=mathutils.Vector((0,0,-_mz3)),verts=_bm3.verts)
    _bm3.to_mesh(_obj.data); _bm3.free(); _obj.data.update()
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.11399999999999999], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['u_bracket_27be47'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('u_bracket_27be47')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: u_bracket_27be47')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_u_bracket_15'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_u_bracket_15'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('u_bracket_27be47')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('u_bracket_27be47')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('u_bracket_27be47')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_dccceb4172f3_9cbba46fa2') or bpy.data.materials.new('MatPBR_dccceb4172f3_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.38005633644979925, 0.38005633644979925, 0.40644830114675407, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 1.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.35
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')

# --- PIPELINE FLUSH CHUNK ---
import bpy, bmesh, json, math, mathutils
_coll_name = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
if _coll_name not in bpy.data.collections:
    _c = bpy.data.collections.new(_coll_name)
    bpy.context.scene.collection.children.link(_c)
_coll = bpy.data.collections.get(_coll_name)
def _link(obj):
    if _coll: _coll.objects.link(obj)
    else: bpy.context.scene.collection.objects.link(obj)
def _unlink_all(obj):
    for c in list(obj.users_collection): c.objects.unlink(obj)
_sentinel_results = {}
# ── assembly: bracket_assembly ──
_e = bpy.data.objects.new('bracket_assembly_assembly_368f22', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.16599999999999998], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('build_a_detailed_tabletop_retro_futurist_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['u_shape_bracket_25de42', 'camera_lens_holder_9bfccb']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['bracket_assembly_assembly_368f22'] = list(_e.matrix_world.translation)
# ── assembly: landing_feet ──
_e = bpy.data.objects.new('landing_feet_assembly_8c9412', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, -0.074], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('build_a_detailed_tabletop_retro_futurist_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['landing_feet_front_left_35fddc', 'landing_feet_front_right_28d011', 'landing_feet_rear_left_32eb7d', 'landing_feet_rear_right_c0613e']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['landing_feet_assembly_8c9412'] = list(_e.matrix_world.translation)
if 'propeller_blade_back_2_6f6b4c' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.04)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_back_2_6f6b4c'; _obj.data.name = 'propeller_blade_back_2_6f6b4c'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.01], [-1.0, 6.123233995736766e-17, 0.0, 0.119], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_back_2_6f6b4c'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_back_2_6f6b4c')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_back_2_6f6b4c')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_back_2_33'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_propeller_blade_back_2_33'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_back_2_6f6b4c')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_back_2_6f6b4c')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_back_2_6f6b4c')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_back_3_c4e3b2' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.047)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_back_3_c4e3b2'; _obj.data.name = 'propeller_blade_back_3_c4e3b2'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.01], [-1.0, 6.123233995736766e-17, 0.0, 0.119], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_back_3_c4e3b2'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_back_3_c4e3b2')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_back_3_c4e3b2')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_back_3_34'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_back_12/m_f4b618e2bc_propeller_blade_back_3_34'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_back_3_c4e3b2')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_back_3_c4e3b2')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_back_3_c4e3b2')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_front_2_2c1ea8' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.04)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_front_2_2c1ea8'; _obj.data.name = 'propeller_blade_front_2_2c1ea8'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.01], [-1.0, 6.123233995736766e-17, 0.0, -0.119], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_front_2_2c1ea8'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_front_2_2c1ea8')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_front_2_2c1ea8')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_front_2_26'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_propeller_blade_front_2_26'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_front_2_2c1ea8')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_front_2_2c1ea8')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_front_2_2c1ea8')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_front_3_a665cf' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.008, depth=0.045)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_front_3_a665cf'; _obj.data.name = 'propeller_blade_front_3_a665cf'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.01], [-1.0, 6.123233995736766e-17, 0.0, -0.119], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_front_3_a665cf'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_front_3_a665cf')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_front_3_a665cf')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_front_3_27'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_front_11/m_f4b618e2bc_propeller_blade_front_3_27'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_front_3_a665cf')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_front_3_a665cf')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_front_3_a665cf')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_left_2_d7c4e0' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_left_2_d7c4e0'; _obj.data.name = 'propeller_blade_left_2_d7c4e0'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, -0.175], [-1.0, 6.123233995736766e-17, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_left_2_d7c4e0'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_left_2_d7c4e0')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_left_2_d7c4e0')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_left_2_40'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_propeller_blade_left_2_40'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_left_2_d7c4e0')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_left_2_d7c4e0')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_left_2_d7c4e0')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_left_3_375b18' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_left_3_375b18'; _obj.data.name = 'propeller_blade_left_3_375b18'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, -0.175], [-1.0, 6.123233995736766e-17, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_left_3_375b18'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_left_3_375b18')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_left_3_375b18')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_left_3_41'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_left_13/m_f4b618e2bc_propeller_blade_left_3_41'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_left_3_375b18')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_left_3_375b18')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_left_3_375b18')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_right_2_307117' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_right_2_307117'; _obj.data.name = 'propeller_blade_right_2_307117'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.195], [-1.0, 6.123233995736766e-17, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_right_2_307117'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_right_2_307117')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_right_2_307117')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_right_2_47'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_propeller_blade_right_2_47'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_right_2_307117')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_right_2_307117')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_right_2_307117')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'propeller_blade_right_3_fa997d' not in bpy.data.objects:
    bpy.ops.mesh.primitive_cone_add(radius1=0.004, depth=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'propeller_blade_right_3_fa997d'; _obj.data.name = 'propeller_blade_right_3_fa997d'
    _obj.matrix_world = mathutils.Matrix([[6.123233995736766e-17, 1.0, 0.0, 0.195], [-1.0, 6.123233995736766e-17, 0.0, 0.0], [0.0, 0.0, 1.0, 0.023500000000000004], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['propeller_blade_right_3_fa997d'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('propeller_blade_right_3_fa997d')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: propeller_blade_right_3_fa997d')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_propeller_blade_right_3_48'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_chassis_assembly_1/m_f4b618e2bc_arm_right_14/m_f4b618e2bc_propeller_blade_right_3_48'
_id_obj['sentinel_declared_modifiers'] = json.dumps([], sort_keys=True)

_mod_obj = bpy.data.objects.get('propeller_blade_right_3_fa997d')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.004, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}, {'type': 'subdivision', 'name': None, 'apply': True, 'subdivision_levels': 1, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('propeller_blade_right_3_fa997d')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('propeller_blade_right_3_fa997d')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_2f2508876f02_9cbba46fa2') or bpy.data.materials.new('MatPBR_2f2508876f02_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.6038273388553378, 0.6038273388553378, 0.6038273388553378, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.15
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')

# --- PIPELINE FLUSH CHUNK ---
import bpy, bmesh, json, math, mathutils
_coll_name = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
if _coll_name not in bpy.data.collections:
    _c = bpy.data.collections.new(_coll_name)
    bpy.context.scene.collection.children.link(_c)
_coll = bpy.data.collections.get(_coll_name)
def _link(obj):
    if _coll: _coll.objects.link(obj)
    else: bpy.context.scene.collection.objects.link(obj)
def _unlink_all(obj):
    for c in list(obj.users_collection): c.objects.unlink(obj)
_sentinel_results = {}
# ── assembly: arm_assembly ──
_e = bpy.data.objects.new('arm_assembly_assembly_e8f70b', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.265], [0.0, 1.0, 0.0, -0.1525], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('build_a_detailed_tabletop_retro_futurist_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['arm_assembly_root_9ca86d', 'arm_inner_collar_1_8dbfbe', 'arm_inner_collar_2_771e3b', 'arm_inner_collar_3_6ed7ec', 'arm_inner_collar_4_e77c4f', 'arm_inner_collar_5_d8bbc2', 'rotor_guard_1_d5f942', 'rotor_guard_2_54b27b', 'rotor_guard_3_cda35f', 'rotor_guard_4_daa403', 'rotor_guard_5_206789', 'rotor_hub_1_fa740e']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['arm_assembly_assembly_e8f70b'] = list(_e.matrix_world.translation)
# ── assembly: arm_back ──
_e = bpy.data.objects.new('arm_back_assembly_d86771', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.119], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('chassis_assembly_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['arm_back_cylinder_f8c5c3', 'collar_back_da3663', 'guard_back_b4707c', 'hub_back_00a00b', 'propeller_blade_back_1_1084ab', 'propeller_blade_back_2_6f6b4c', 'propeller_blade_back_3_c4e3b2']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['arm_back_assembly_d86771'] = list(_e.matrix_world.translation)
# ── assembly: arm_front ──
_e = bpy.data.objects.new('arm_front_assembly_d0aca0', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, -0.119], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('chassis_assembly_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['arm_front_cylinder_b7d100', 'collar_front_391248', 'guard_front_6326a4', 'hub_front_525e50', 'propeller_blade_front_1_ef209d', 'propeller_blade_front_2_2c1ea8', 'propeller_blade_front_3_a665cf']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['arm_front_assembly_d0aca0'] = list(_e.matrix_world.translation)
# ── assembly: arm_left ──
_e = bpy.data.objects.new('arm_left_assembly_5a7c53', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, -0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('chassis_assembly_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['arm_left_cylinder_d9531f', 'collar_left_d2c7d8', 'guard_left_64b0fa', 'hub_left_8f2c8a', 'propeller_blade_left_1_3fca5e', 'propeller_blade_left_2_d7c4e0', 'propeller_blade_left_3_375b18']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['arm_left_assembly_5a7c53'] = list(_e.matrix_world.translation)
# ── assembly: arm_right ──
_e = bpy.data.objects.new('arm_right_assembly_0ea8eb', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.185], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('chassis_assembly_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['arm_right_cylinder_9e0196', 'collar_right_62df8a', 'guard_right_a4d51a', 'hub_right_4f33e2', 'propeller_blade_right_1_cbccc4', 'propeller_blade_right_2_307117', 'propeller_blade_right_3_fa997d']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['arm_right_assembly_0ea8eb'] = list(_e.matrix_world.translation)
# ── assembly: chassis_assembly ──
_e = bpy.data.objects.new('chassis_assembly_assembly_3c7ae9', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
_pe = next((o for o in bpy.data.objects if o.name.startswith('build_a_detailed_tabletop_retro_futurist_assembly_') and o.type == 'EMPTY'), None)
if _pe:
    _world = _e.matrix_world.copy()
    _e.parent = _pe
    _e.matrix_parent_inverse = _pe.matrix_world.inverted()
    _e.matrix_world = _world
for _cn in ['chassis_base_3d1a2c', 'status_dome__sembly_1_02_c66f18', 'arm_front_assembly_d0aca0', 'arm_back_assembly_d86771', 'arm_left_assembly_5a7c53', 'arm_right_assembly_0ea8eb', 'u_bracket_27be47', 'camera_lens_ed4799', 'sensor_barrel__sembly_1_09_9011fe', 'sensor_lens_719dca', 'battery_module__sembly_1_11_570249', 'led_1_0d4589']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['chassis_assembly_assembly_3c7ae9'] = list(_e.matrix_world.translation)
if 'battery_module_bbd346' not in bpy.data.objects:
    _mesh = bpy.data.meshes.new('battery_module_bbd346')
    _bm = bmesh.new()
    bmesh.ops.create_cube(_bm, size=1.0)
    for _v in _bm.verts: _v.co.x*=0.03; _v.co.y*=0.02; _v.co.z*=0.015
    _bm.to_mesh(_mesh); _bm.free()
    _obj = bpy.data.objects.new('battery_module_bbd346', _mesh)
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.09999999999999999], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    _link(_obj)
    _sentinel_results['battery_module_bbd346'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('battery_module_bbd346')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: battery_module_bbd346')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_battery_module_7'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_battery_module_7'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('battery_module_bbd346')
if _mod_obj:
    for _ms in [{'type': 'bevel', 'name': None, 'apply': True, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.002, 'bevel_segments': 2, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('battery_module_bbd346')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('battery_module_bbd346')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_1707af06c991_9cbba46fa2') or bpy.data.materials.new('MatPBR_1707af06c991_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.5
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 1.0
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 0.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 0.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if [0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0] and 3.0 > 0:
            _em = tuple([0.692071056865372, 0.002708978328173375, 0.0019349845201238392, 1.0])
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 3.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (0.0 > 0 or 1.0 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

if 'status_dome_67b3cb' not in bpy.data.objects:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025)
    _obj = bpy.context.active_object
    _obj.name = 'status_dome_67b3cb'; _obj.data.name = 'status_dome_67b3cb'
    _bm2 = bmesh.new(); _bm2.from_mesh(_obj.data)
    _geom2 = _bm2.verts[:]+_bm2.edges[:]+_bm2.faces[:]
    bmesh.ops.bisect_plane(_bm2,geom=_geom2,plane_co=(0,0,0),plane_no=(0,0,1),clear_inner=True,clear_outer=False)
    bmesh.ops.remove_doubles(_bm2,verts=_bm2.verts,dist=0.0001)
    _bnd=[e for e in _bm2.edges if len(e.link_faces)==1]
    if _bnd: bmesh.ops.edgeloop_fill(_bm2,edges=_bnd)
    _bm2.to_mesh(_obj.data); _bm2.free()
    _obj.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.025], [0.0, 0.0, 0.0, 1.0]])
    _unlink_all(_obj); _link(_obj)
    _sentinel_results['status_dome_67b3cb'] = list(_obj.matrix_world.translation)

_id_obj = bpy.data.objects.get('status_dome_67b3cb')
if not _id_obj: raise RuntimeError('Created object missing before identity tagging: status_dome_67b3cb')
_id_obj['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
_id_obj['sentinel_attempt_id'] = '9cbba46fa2'
_id_obj['sentinel_node_id'] = 'm_f4b618e2bc_status_dome_2'
_id_obj['sentinel_canonical_path'] = '/m_f4b618e2bc_root/m_f4b618e2bc_status_dome_2'
_id_obj['sentinel_declared_modifiers'] = json.dumps([{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}], sort_keys=True)

_mod_obj = bpy.data.objects.get('status_dome_67b3cb')
if _mod_obj:
    for _ms in [{'type': 'smooth', 'name': None, 'apply': False, 'subdivision_levels': 2, 'subdivision_render_levels': 2, 'subdivision_type': 'CATMULL_CLARK', 'bevel_width': 0.02, 'bevel_segments': 3, 'bevel_limit_method': 'ANGLE', 'bevel_angle_limit': 30.0, 'bevel_profile': 0.5, 'solidify_thickness': 0.01, 'solidify_offset': -1.0, 'solidify_even_thickness': True, 'mirror_axis': [True, False, False], 'mirror_merge': True, 'mirror_merge_threshold': 0.001, 'array_count': 2, 'array_offset': [1.0, 0.0, 0.0], 'array_use_relative_offset': True, 'deform_method': 'BEND', 'deform_angle': 0.0, 'deform_factor': 0.0, 'deform_axis': 'X', 'weighted_normal_weight': 50, 'weighted_normal_keep_sharp': True, 'smooth_factor': 0.5, 'smooth_iterations': 1, 'edge_split_angle': 30.0, 'decimate_ratio': 0.5, 'decimate_type': 'COLLAPSE'}]:
            _mt = _ms.get('type','')
            if _mt == 'bevel':
                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')
                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]
                _min_d = min(_dims) if _dims else 0.1
                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))
                _m.segments = _ms.get('bevel_segments',3)
                _m.use_clamp_overlap = True
            elif _mt == 'subdivision':
                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')
                _m.levels = _ms.get('subdivision_levels',2)
                _m.render_levels = _ms.get('subdivision_render_levels',2)
            elif _mt == 'solidify':
                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)
            elif _mt == 'mirror':
                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False
            elif _mt == 'array':
                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0
            elif _mt == 'simple_deform':
                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')
            elif _mt == 'weighted_normal':
                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)
            elif _mt == 'smooth':
                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)
            elif _mt == 'edge_split':
                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))
            elif _mt == 'triangulate':
                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')
            elif _mt == 'decimate':
                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')
            else:
                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))
            if _ms.get('apply',True):
                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)

_cl_obj = bpy.data.objects.get('status_dome_67b3cb')
if _cl_obj and _cl_obj.type == 'MESH':
    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)
    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)
    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)
    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()

_mat_obj = bpy.data.objects.get('status_dome_67b3cb')
if _mat_obj:
    _mat = bpy.data.materials.get('MatPBR_c80665234ee2_9cbba46fa2') or bpy.data.materials.new('MatPBR_c80665234ee2_9cbba46fa2')
    _mat.use_nodes = True
    _mat['sentinel_build_id'] = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
    if _bsdf:
        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = (0.0030959752321981426, 0.033104766570885055, 0.7874122893956174, 0.05)
        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = 0.0
        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = 0.0
        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = 1.45
        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = 0.05
        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = 1.0
        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = 1.0
        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = 0.0
        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = 0.0
        if 'Subsurface Tint' in _bsdf.inputs and None: _bsdf.inputs['Subsurface Tint'].default_value = tuple(None)
        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.2, 0.1)
        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = 0.0
        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = 0.0
        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = 0.03
        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = 0.03
        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = 0.0
        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = 0.0
        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = 0.5
        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = (1.0, 1.0, 1.0, 1.0)
        if None and 0.0 > 0:
            _em = tuple(None)
            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em
            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em
            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = 0.0
    _mat['sentinel_normal_strength'] = 1.0
    _mat['sentinel_blend_mode'] = 'opaque'
    if hasattr(_mat, 'surface_render_method') and 'opaque' != 'opaque': _mat.surface_render_method = 'DITHERED' if 'opaque' == 'dithered' else 'BLENDED'
    elif hasattr(_mat, 'surface_render_method') and (1.0 > 0 or 0.05 < 1): _mat.surface_render_method = 'DITHERED'
    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):
        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)
        else: _mat_obj.data.materials[0] = _mat

print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')

# --- PIPELINE FLUSH CHUNK ---
import bpy, bmesh, json, math, mathutils
_coll_name = 'Sentinel_Build_cc53f529434d_9cbba46fa2'
if _coll_name not in bpy.data.collections:
    _c = bpy.data.collections.new(_coll_name)
    bpy.context.scene.collection.children.link(_c)
_coll = bpy.data.collections.get(_coll_name)
def _link(obj):
    if _coll: _coll.objects.link(obj)
    else: bpy.context.scene.collection.objects.link(obj)
def _unlink_all(obj):
    for c in list(obj.users_collection): c.objects.unlink(obj)
_sentinel_results = {}
# ── assembly: build_a_detailed_tabletop_retro_futurist ──
_e = bpy.data.objects.new('build_a_detailed_tabletop_retro_futurist_assembly_820d86', None)
_e.empty_display_type = 'PLAIN_AXES'
_e.empty_display_size = 0.5
_e.matrix_world = mathutils.Matrix([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [-0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
_unlink_all(_e) if _e.users_collection else None
_link(_e)
for _cn in ['chassis_assembly_assembly_3c7ae9', 'status_dome_67b3cb', 'arm_assembly_assembly_e8f70b', 'bracket_assembly_assembly_368f22', 'camera_module_2e36d8', 'sensor_barrel_92e6c0', 'battery_module_bbd346', 'landing_feet_assembly_8c9412']:
    _co = bpy.data.objects.get(_cn)
    if _co:
        _world = _co.matrix_world.copy()
        _co.parent = _e
        _co.matrix_parent_inverse = _e.matrix_world.inverted()
        _co.matrix_world = _world
_sentinel_results['build_a_detailed_tabletop_retro_futurist_assembly_820d86'] = list(_e.matrix_world.translation)
print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')


# --- STANDALONE RENDER VERIFICATION FOOTER ---
import bpy, os
render_dir = r"C:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\data\renders_pipeline_compiled"
os.makedirs(render_dir, exist_ok=True)

# Add Camera & Sun if not present
cam_data = bpy.data.cameras.new("PipelineCamera")
cam_obj = bpy.data.objects.new("PipelineCamera", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

light_data = bpy.data.lights.new(name="PipelineSun", type='SUN')
light_data.energy = 3.5
light_obj = bpy.data.objects.new(name="PipelineSun", object_data=light_data)
bpy.context.scene.collection.objects.link(light_obj)
light_obj.rotation_euler = (0.785, 0.35, 0.785)

scene = bpy.context.scene
scene.render.resolution_x = 800
scene.render.resolution_y = 600
scene.render.film_transparent = True

views = {
    "isometric.png": ((0.5, -0.6, 0.4), (1.05, 0.0, 0.785)),
    "front.png":     ((0.0, -0.7, 0.1), (1.57, 0.0, 0.0)),
    "side.png":      ((0.7, 0.0, 0.1),  (1.57, 0.0, 1.57)),
    "top.png":       ((0.0, 0.0, 0.7),  (0.0, 0.0, 0.0)),
}

for filename, (loc, rot) in views.items():
    cam_obj.location = loc
    cam_obj.rotation_euler = rot
    scene.render.filepath = os.path.join(render_dir, filename)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {scene.render.filepath}")

print("PIPELINE_STANDALONE_BUILD_AND_RENDER_COMPLETE")
