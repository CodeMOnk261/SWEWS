import bpy
import math
import random
import json
import os

# Configurations
COLLECTION_NAME = "SpaceWeatherSim"

# Global dictionary to store base coordinates of magnetic field splines for animation wiggling
original_spline_points = {}

def clean_previous_sim():
    """Completely deletes spawned simulation objects, keeping user modeled objects intact."""
    global original_spline_points
    original_spline_points = {}

    # 1. Unregister any existing frame handlers
    for h in list(bpy.app.handlers.frame_change_pre):
        if h.__name__ in ["solar_wind_anim_handler", "real_data_anim_handler"]:
            bpy.app.handlers.frame_change_pre.remove(h)

    # 2. Deletion prefixes list for spawned-only objects
    prefixes = [
        "Earth_Atmosphere", "Earth_Clouds", "Sun_Sphere", "WindParticle_", "Star_",
        "StatusHUD", "SimCamera", "SimSun", "SW_IMF_Line_", "VanAllen_Inner", "VanAllen_Outer"
    ]
    
    # Delete spawned objects from the collection if it exists
    col = bpy.data.collections.get(COLLECTION_NAME)
    if col:
        for obj in list(col.objects):
            should_delete = False
            for pfx in prefixes:
                if obj.name.startswith(pfx):
                    should_delete = True
                    break
            if should_delete:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
                
    # Delete any duplicate/orphaned spawned objects in the database
    for obj in list(bpy.data.objects):
        should_delete = False
        for pfx in prefixes:
            if obj.name.startswith(pfx):
                should_delete = True
                break
        if should_delete:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
                
    # Clean up spawned materials to prevent name increments
    mats_to_delete = [
        "CloudsHighResMat", "HUDTextMat", "OrbitMat", 
        "SatBodyMat", "SatPanelMat", "SatBubbleMat", 
        "BowShockMat", "VanAllenInnerMat", "VanAllenOuterMat", 
        "HUDLabelMat", "StarMat", "SunMat", "SolarWindLineMat"
    ]
    for mat_name in mats_to_delete:
        mat = bpy.data.materials.get(mat_name)
        if mat:
            bpy.data.materials.remove(mat)

    # Create collection if it was removed
    if not col:
        col = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(col)
    
    # Set active collection
    for layer_col in bpy.context.view_layer.layer_collection.children:
        if layer_col.name == COLLECTION_NAME:
            bpy.context.view_layer.active_layer_collection = layer_col
            break

def create_glow_material(name, color=(0.0, 1.0, 1.0, 1.0), strength=2.0):
    """Creates a basic glowing material compatible with all Blender versions."""
    mat = bpy.data.materials.get(name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    node_emission = nodes.new(type='ShaderNodeEmission')
    node_emission.inputs['Color'].default_value = color
    node_emission.inputs['Strength'].default_value = strength
    
    node_output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(node_emission.outputs['Emission'], node_output.inputs['Surface'])
    return mat

def setup_space_environment():
    """Configures space black scene background, hides grid overlays."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new(name="SpaceWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes.clear()
    
    bg = nodes.new(type='ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0) # Pitch black space
    bg.inputs['Strength'].default_value = 1.0
    
    output = nodes.new(type='ShaderNodeOutputWorld')
    world.node_tree.links.new(bg.outputs['Background'], output.inputs['Surface'])
        
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    try:
                        space.overlay.show_floor = False
                        space.overlay.show_ortho_grid = False
                        space.overlay.show_axis_x = False
                        space.overlay.show_axis_y = False
                        space.overlay.show_axis_z = False
                    except AttributeError:
                        pass
                    
    # Generate Starfield (120 tiny glowing stars scattered around)
    col = bpy.data.collections.get(COLLECTION_NAME)
    star_mat = create_glow_material("StarMat", color=(1.0, 1.0, 1.0, 1.0), strength=3.5)
    
    for i in range(120):
        theta = random.uniform(0, 2 * math.pi)
        phi = math.acos(random.uniform(-1, 1))
        r = random.uniform(25, 45)
        
        x = r * math.sin(phi) * math.cos(theta)
        y = r * math.sin(phi) * math.sin(theta)
        z = r * math.cos(phi)
        
        bpy.ops.mesh.primitive_ico_sphere_add(radius=0.07, subdivisions=1, location=(x, y, z))
        star = bpy.context.active_object
        star.name = f"Star_{i}"
        star.data.materials.append(star_mat)
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(star)
                col.objects.link(star)
            except:
                pass

def setup_earth_material_nodes(mat):
    """Configures PBR textures mapping for realistic Day/Night Earth sphere using low-res textures."""
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    
    # 1. Diffuse
    img_diff = nodes.new(type='ShaderNodeTexImage')
    img_diff.image = bpy.data.images.load("E:/Space_Weather_pre/scripts/Texture/Low res/Albedo-diffuse_Low-end.jpg")
    links.new(tex_coord.outputs['Generated'], img_diff.inputs['Vector'])
    links.new(img_diff.outputs['Color'], principled.inputs['Base Color'])
    
    # 2. Specular/Roughness
    img_spec = nodes.new(type='ShaderNodeTexImage')
    img_spec.image = bpy.data.images.load("E:/Space_Weather_pre/scripts/Texture/Low res/Ocean_Mask.png")
    try:
        img_spec.image.colorspace_settings.name = 'Non-Color'
    except:
        pass
    links.new(tex_coord.outputs['Generated'], img_spec.inputs['Vector'])
    
    map_rough = nodes.new(type='ShaderNodeMapRange')
    map_rough.inputs['To Min'].default_value = 0.85 # Land
    map_rough.inputs['To Max'].default_value = 0.05 # Ocean
    links.new(img_spec.outputs['Color'], map_rough.inputs['Value'])
    links.new(map_rough.outputs['Result'], principled.inputs['Roughness'])
    
    # 3. Bump Mapping
    img_bump = nodes.new(type='ShaderNodeTexImage')
    img_bump.image = bpy.data.images.load("E:/Space_Weather_pre/scripts/Texture/Low res/Bump_Low-end.jpg")
    try:
        img_bump.image.colorspace_settings.name = 'Non-Color'
    except:
        pass
    links.new(tex_coord.outputs['Generated'], img_bump.inputs['Vector'])
    
    bump = nodes.new(type='ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.22
    links.new(img_bump.outputs['Color'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], principled.inputs['Normal'])
    
    # 4. Night Lights emission masked by terminator (light source from -X)
    img_lights = nodes.new(type='ShaderNodeTexImage')
    img_lights.image = bpy.data.images.load("E:/Space_Weather_pre/scripts/Texture/Low res/night_lights_modified_Low-end.png")
    links.new(tex_coord.outputs['Generated'], img_lights.inputs['Vector'])
    
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    links.new(tex_coord.outputs['Normal'], sep.inputs['Vector'])
    
    # Multiply by -0.5 to align day side with Sun at -X
    math_mul = nodes.new(type='ShaderNodeMath')
    math_mul.operation = 'MULTIPLY'
    math_mul.inputs[1].default_value = -0.5
    links.new(sep.outputs['X'], math_mul.inputs[0])
    
    math_add = nodes.new(type='ShaderNodeMath')
    math_add.operation = 'ADD'
    math_add.inputs[1].default_value = 0.5
    links.new(math_mul.outputs['Value'], math_add.inputs[0])
    
    inv_mask = nodes.new(type='ShaderNodeMath')
    inv_mask.operation = 'SUBTRACT'
    inv_mask.inputs[0].default_value = 1.0
    links.new(math_add.outputs['Value'], inv_mask.inputs[1])
    
    mix_lights = nodes.new(type='ShaderNodeMix')
    mix_lights.data_type = 'RGBA'
    mix_lights.blend_type = 'MIX'
    links.new(inv_mask.outputs['Value'], mix_lights.inputs[0]) # Factor
    mix_lights.inputs[6].default_value = (0.0, 0.0, 0.0, 1.0) # Day is black
    links.new(img_lights.outputs['Color'], mix_lights.inputs[7]) # Night lights
    
    if 'Emission Color' in principled.inputs:
        links.new(mix_lights.outputs[2], principled.inputs['Emission Color'])
        principled.inputs['Emission Strength'].default_value = 4.5
    elif 'Emission' in principled.inputs:
        links.new(mix_lights.outputs[2], principled.inputs['Emission'])

def setup_clouds_material_nodes(mat):
    """Sets up transparent clouds layer material using low-res clouds."""
    mat.use_nodes = True
    try:
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'NONE'
    except AttributeError:
        pass
        
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    img_clouds = nodes.new(type='ShaderNodeTexImage')
    img_clouds.image = bpy.data.images.load("E:/Space_Weather_pre/scripts/Texture/Low res/Clouds_Low-end.png")
    links.new(tex_coord.outputs['Generated'], img_clouds.inputs['Vector'])
    
    principled.inputs['Base Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    links.new(img_clouds.outputs['Alpha'], principled.inputs['Alpha'])
    principled.inputs['Roughness'].default_value = 0.9

def create_atmosphere_material():
    """Generates a semi-transparent atmosphere glow material lit by the Sun (-X)."""
    mat = bpy.data.materials.get("AtmosphereMat")
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name="AtmosphereMat")
    mat.use_nodes = True
    try:
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'NONE'
    except AttributeError:
        pass
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    weight = nodes.new(type='ShaderNodeLayerWeight')
    weight.inputs['Blend'].default_value = 0.22
    
    power = nodes.new(type='ShaderNodeMath')
    power.operation = 'POWER'
    power.inputs[1].default_value = 5.0
    links.new(weight.outputs['Facing'], power.inputs[0])
    
    inv = nodes.new(type='ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    links.new(power.outputs['Value'], inv.inputs[1])
    
    coord = nodes.new(type='ShaderNodeTexCoord')
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Normal'], sep.inputs['Vector'])
    
    math_mul = nodes.new(type='ShaderNodeMath')
    math_mul.operation = 'MULTIPLY'
    math_mul.inputs[1].default_value = -0.5
    links.new(sep.outputs['X'], math_mul.inputs[0])
    
    math_add = nodes.new(type='ShaderNodeMath')
    math_add.operation = 'ADD'
    math_add.inputs[1].default_value = 0.52
    links.new(math_mul.outputs['Value'], math_add.inputs[0])
    
    final_alpha = nodes.new(type='ShaderNodeMath')
    final_alpha.operation = 'MULTIPLY'
    links.new(inv.outputs['Value'], final_alpha.inputs[0])
    links.new(math_add.outputs['Value'], final_alpha.inputs[1])
    
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = (0.25, 0.65, 1.0, 1.0)
    emission.inputs['Strength'].default_value = 3.5
    
    transparent = nodes.new(type='ShaderNodeBsdfTransparent')
    mix = nodes.new(type='ShaderNodeMixShader')
    
    links.new(final_alpha.outputs['Value'], mix.inputs[0])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(mix.outputs['Shader'], output.inputs['Surface'])
    
    return mat

def create_bow_shock_material(state="SAFE"):
    """Generates an extremely transparent, wavelike plasma bow shock wave front (barely visible light)."""
    mat = bpy.data.materials.get("BowShockMat")
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name="BowShockMat")
    mat.use_nodes = True
    try:
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'NONE'
    except AttributeError:
        pass
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    if state == "SEVERE":
        color = (1.0, 0.08, 0.08, 1.0)
        strength = 4.5
    elif state == "MODERATE":
        color = (1.0, 0.5, 0.0, 1.0)
        strength = 2.8
    else:
        color = (0.1, 0.8, 1.0, 1.0)
        strength = 1.5
        
    # Texture Coord & Mapping to animate scrolling plasma ripples
    coord = nodes.new(type='ShaderNodeTexCoord')
    mapping = nodes.new(type='ShaderNodeMapping')
    mapping.name = "ShockMapping"
    links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    
    noise = nodes.new(type='ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 7.0
    noise.inputs['Detail'].default_value = 4.0
    links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
    
    # Layer Weight (Fresnel-like) to keep the center empty and only edge glow
    weight = nodes.new(type='ShaderNodeLayerWeight')
    weight.inputs['Blend'].default_value = 0.28
    
    inv = nodes.new(type='ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    links.new(weight.outputs['Facing'], inv.inputs[1])
    
    # Combine Noise & Layer Weight
    mul = nodes.new(type='ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    links.new(inv.outputs['Value'], mul.inputs[0])
    links.new(noise.outputs['Fac'], mul.inputs[1])
    
    # Extremely low base multiplier for barely-visible, non-solid light wave front
    alpha = nodes.new(type='ShaderNodeMath')
    alpha.operation = 'MULTIPLY'
    alpha.inputs[1].default_value = 0.02 # Extremely faint light!
    links.new(mul.outputs['Value'], alpha.inputs[0])
    
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = strength
    
    transparent = nodes.new(type='ShaderNodeBsdfTransparent')
    mix = nodes.new(type='ShaderNodeMixShader')
    
    links.new(alpha.outputs['Value'], mix.inputs[0])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(mix.outputs['Shader'], output.inputs['Surface'])
    
    return mat

def setup_van_allen_material(name, color=(0.1, 1.0, 0.4, 1.0), base_a=0.015):
    """Sets up an extremely transparent, soft glowing haze material (light-like, non-solid)."""
    mat = bpy.data.materials.get(name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    try:
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'NONE'
    except AttributeError:
        pass
        
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    # Soft grazing-angle glow (transparent in center, soft fuzzy light at edges)
    weight = nodes.new(type='ShaderNodeLayerWeight')
    weight.inputs['Blend'].default_value = 0.18
    
    inv = nodes.new(type='ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    links.new(weight.outputs['Facing'], inv.inputs[1])
    
    # Multiply by a very low base alpha so it is barely visible dust/light
    alpha = nodes.new(type='ShaderNodeMath')
    alpha.operation = 'MULTIPLY'
    alpha.inputs[1].default_value = base_a
    links.new(inv.outputs['Value'], alpha.inputs[0])
    
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = 1.0
    
    transparent = nodes.new(type='ShaderNodeBsdfTransparent')
    mix = nodes.new(type='ShaderNodeMixShader')
    
    links.new(alpha.outputs['Value'], mix.inputs[0])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(mix.outputs['Shader'], output.inputs['Surface'])
    
    return mat

def build_earth():
    """Integrates user's modeled Sphere as Earth, applying low-res PBR texture shaders."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    earth = bpy.data.objects.get("Sphere")
    
    if earth:
        print("Integrating user Sphere as Earth_Solid")
        earth.name = "Earth_Solid"
    else:
        earth = bpy.data.objects.get("Earth_Solid")
        
    if earth:
        earth.location = (0, 0, 0)
        bpy.ops.object.shade_smooth()
        
        # Scale to radius 1.0 (dimensions 2.0, default for default sphere)
        max_d = max(earth.dimensions)
        if max_d > 0.001:
            s = 2.0 / max_d
            earth.scale = (s, s, s)
            
        mat_earth = bpy.data.materials.new("EarthHighResMat")
        setup_earth_material_nodes(mat_earth)
        earth.data.materials.clear()
        earth.data.materials.append(mat_earth)
        
        if col and earth.name not in col.objects.keys():
            try:
                col.objects.link(earth)
            except:
                pass
    else:
        # Fallback to UV Sphere
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2.0, location=(0, 0, 0))
        earth = bpy.context.active_object
        earth.name = "Earth_Solid"
        bpy.ops.object.shade_smooth()
        mat_earth = bpy.data.materials.new("EarthHighResMat")
        setup_earth_material_nodes(mat_earth)
        earth.data.materials.append(mat_earth)
        if col:
            col.objects.link(earth)

    # Atmosphere glow halo shell
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.08, location=(0, 0, 0))
    earth_atmos = bpy.context.active_object
    earth_atmos.name = "Earth_Atmosphere"
    bpy.ops.object.shade_smooth()
    earth_atmos.data.materials.append(create_atmosphere_material())
    if col:
        try:
            bpy.context.scene.collection.objects.unlink(earth_atmos)
            col.objects.link(earth_atmos)
        except:
            pass

    # Clouds overlay shell
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.04, location=(0, 0, 0))
    earth_clouds = bpy.context.active_object
    earth_clouds.name = "Earth_Clouds"
    bpy.ops.object.shade_smooth()
    mat_clouds = bpy.data.materials.new("CloudsHighResMat")
    setup_clouds_material_nodes(mat_clouds)
    earth_clouds.data.materials.append(mat_clouds)
    if col:
        try:
            bpy.context.scene.collection.objects.unlink(earth_clouds)
            col.objects.link(earth_clouds)
        except:
            pass

def build_sun():
    """Generates the Sun sphere model at -X distance (left side)."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=4.5, location=(-30, 0, 0))
    sun = bpy.context.active_object
    sun.name = "Sun_Sphere"
    bpy.ops.object.shade_smooth()
    sun_color = (1.0, 0.78, 0.2, 1.0)
    sun.data.materials.append(create_glow_material("SunMat", color=sun_color, strength=6.0))

def build_magnetosphere():
    """Integrates and parents user's modeled FieldLines curve, wiggling splines procedurally."""
    global original_spline_points
    original_spline_points = {}
    col = bpy.data.collections.get(COLLECTION_NAME)
    
    # 1. Create Anchor Empty
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0))
    anchor = bpy.context.active_object
    anchor.name = "Magnetosphere_Anchor"
    if col:
        try:
            bpy.context.scene.collection.objects.unlink(anchor)
            col.objects.link(anchor)
        except:
            pass

    # Standard material
    mag_mat = create_glow_material("MagnetoMat", color=(0.0, 0.55, 1.0, 1.0), strength=2.2)
    
    f_obj = bpy.data.objects.get("FieldLines")
    if f_obj:
        print("Integrating user FieldLines curves")
        f_obj.location = (0, 0, 0)
        f_obj.data.bevel_depth = 0.015
        f_obj.data.bevel_resolution = 2
        f_obj.data.materials.clear()
        f_obj.data.materials.append(mag_mat)
        
        f_obj.parent = anchor
        if col and f_obj.name not in col.objects.keys():
            try:
                col.objects.link(f_obj)
            except:
                pass
                
        # Store original points of their splines
        original_spline_points["FieldLines"] = []
        for spline in f_obj.data.splines:
            original_spline_points["FieldLines"].append([list(p.co) for p in spline.points])
    else:
        # Fallback to generated curves
        shells = [4.0, 5.5]
        planes = 8
        for s_idx, R_0 in enumerate(shells):
            for p_idx in range(planes):
                phi = (2 * math.pi / planes) * p_idx
                points = []
                steps = 38
                for i in range(steps + 1):
                    theta = 0.08 + (math.pi - 0.16) * (i / steps)
                    r = R_0 * (math.sin(theta) ** 2)
                    x = r * math.sin(theta) * math.cos(phi)
                    y = r * math.sin(theta) * math.sin(phi)
                    z = r * math.cos(theta)
                    if x < 0:
                        x *= 0.65
                        y *= 0.75
                    else:
                        x *= 1.6
                        y *= 1.2
                    x += 0.3
                    points.append((x, y, z))
                    
                name = f"MagField_Shell{s_idx}_Plane{p_idx}"
                curve_data = bpy.data.curves.new(name=name, type='CURVE')
                curve_data.dimensions = '3D'
                spline = curve_data.splines.new('POLY')
                spline.points.add(len(points) - 1)
                for idx, pt in enumerate(points):
                    spline.points[idx].co = (pt[0], pt[1], pt[2], 1.0)
                    
                obj = bpy.data.objects.new(name, curve_data)
                if col:
                    col.objects.link(obj)
                obj.data.bevel_depth = 0.015
                obj.data.bevel_resolution = 2
                obj.data.materials.append(mag_mat)
                obj.parent = anchor
                original_spline_points[name] = [list(p.co) for p in spline.points]

def build_bow_shock_shield():
    """Creates a visible, shimmering plasma bow shock wave front (positioned at -X)."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=3.5, location=(-3.5, 0, 0))
    shield = bpy.context.active_object
    shield.name = "BowShockShield"
    shield.scale = (0.65, 1.2, 1.2)
    shield.data.materials.append(create_bow_shock_material("SAFE"))
    bpy.ops.object.shade_smooth()

def build_van_allen_belts():
    """Generates the Van Allen Belts (Inner and Outer Toruses) with extremely transparent, non-solid light materials."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    
    # 1. Inner belt (barely visible green haze, base alpha = 0.015)
    bpy.ops.mesh.primitive_torus_add(major_radius=2.8, minor_radius=0.25, location=(0,0,0))
    inner = bpy.context.active_object
    inner.name = "VanAllen_Inner"
    bpy.ops.object.shade_smooth()
    inner_mat = setup_van_allen_material("VanAllenInnerMat", color=(0.1, 1.0, 0.4, 1.0), base_a=0.015)
    inner.data.materials.append(inner_mat)
    
    # 2. Outer belt (barely visible blue/cyan haze, base alpha = 0.008)
    bpy.ops.mesh.primitive_torus_add(major_radius=4.5, minor_radius=0.5, location=(0,0,0))
    outer = bpy.context.active_object
    outer.name = "VanAllen_Outer"
    bpy.ops.object.shade_smooth()
    outer_mat = setup_van_allen_material("VanAllenOuterMat", color=(0.0, 0.8, 1.0, 1.0), base_a=0.008)
    outer.data.materials.append(outer_mat)
    
    if col:
        try:
            bpy.context.scene.collection.objects.unlink(inner)
            col.objects.link(inner)
            bpy.context.scene.collection.objects.unlink(outer)
            col.objects.link(outer)
        except:
            pass

def build_solar_wind_lines():
    """Generates 13 golden IMF lines flowing from Sun and bending smoothly around bow shock."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    num_lines = 13
    sw_line_mat = create_glow_material("SolarWindLineMat", color=(1.0, 0.55, 0.08, 1.0), strength=2.2)
    
    for i in range(num_lines):
        y_init = -8.0 + 16.0 * (i / (num_lines - 1))
        z_init = random.uniform(-1.0, 1.0)
        
        points = []
        steps = 42
        for s in range(steps + 1):
            x = -20.0 + 40.0 * (s / steps)
            
            y_curr = y_init
            z_curr = z_init
            
            # Deflect lines smoothly as they approach the day-side magnetopause (around X = -3.5)
            if x < 6.0:
                deflect_amp = 3.6 * math.exp(-((x + 2.0) ** 2) / 12.0)
                if abs(y_init) < 6.2:
                    sign = 1.0 if y_init >= 0 else -1.0
                    if abs(y_init) < 0.01:
                        sign = 1.0 if i % 2 == 0 else -1.0
                    y_curr = y_init + sign * deflect_amp * (1.0 - abs(y_init) / 6.2)
            
            points.append((x, y_curr, z_curr))
            
        name = f"SW_IMF_Line_{i}"
        curve_data = bpy.data.curves.new(name=name, type='CURVE')
        curve_data.dimensions = '3D'
        
        spline = curve_data.splines.new('POLY')
        spline.points.add(len(points) - 1)
        for idx, pt in enumerate(points):
            spline.points[idx].co = (pt[0], pt[1], pt[2], 1.0)
            
        obj = bpy.data.objects.new(name, curve_data)
        if col:
            col.objects.link(obj)
            
        obj.data.bevel_depth = 0.012
        obj.data.bevel_resolution = 2
        obj.data.materials.append(sw_line_mat)

def build_solar_wind_particles():
    """Creates initial solar wind particle spheres color-coded dynamically (red, yellow, blue, orange)."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    p_count = 55
    
    mats = {
        "Red": create_glow_material("PartMat_Red", (1.0, 0.08, 0.08, 1.0), 3.0),
        "Yellow": create_glow_material("PartMat_Yellow", (1.0, 0.85, 0.15, 1.0), 3.0),
        "Blue": create_glow_material("PartMat_Blue", (0.1, 0.65, 1.0, 1.0), 3.0),
        "Orange": create_glow_material("PartMat_Orange", (1.0, 0.48, 0.02, 1.0), 3.0)
    }
    mat_keys = list(mats.keys())
    
    for i in range(p_count):
        bpy.ops.mesh.primitive_ico_sphere_add(radius=0.08, subdivisions=1)
        p = bpy.context.active_object
        p.name = f"WindParticle_{i}"
        
        ckey = random.choice(mat_keys)
        p.data.materials.append(mats[ckey])
        p["color_type"] = ckey
        
        # Spawn near Sun (left side)
        p.location.x = random.uniform(-15, 15)
        p.location.y = random.uniform(-6, 6)
        p.location.z = random.uniform(-6, 6)
        
        p["speed"] = 0.25
        p["offset_factor"] = random.uniform(1.0, 1.35)
        p["init_y"] = p.location.y
        p["init_z"] = p.location.z
        
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(p)
                col.objects.link(p)
            except:
                pass

def build_status_text():
    """Creates a floating HUD-like status text indicating warning status (hidden by default)."""
    bpy.ops.object.text_add(location=(-5.5, -4, 6.5))
    text_obj = bpy.context.active_object
    text_obj.name = "StatusHUD"
    text_obj.data.body = "TIME: --:-- | Dst: -- nT | Speed: --- km/s"
    
    text_obj.rotation_euler = (1.12, 0.0, 0.68)
    text_obj.scale = (0.45, 0.45, 0.45)
    text_obj.data.materials.append(create_glow_material("HUDTextMat", (0.0, 1.0, 0.5, 1.0), strength=3.0))
    
    # Hide HUD by default
    text_obj.hide_viewport = True
    text_obj.hide_render = True

def build_labels():
    """Creates static analytical HUD labels pointing to magnetosphere structures (hidden by default)."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    label_mat = create_glow_material("HUDLabelMat", (0.8, 0.8, 0.9, 0.5), strength=1.5)
    
    labels = [
        ("SOLAR WIND", (11.0, 4.0, 0.0)),
        ("BOW SHOCK", (4.8, 3.2, 0.0)),
        ("MAGNETOPAUSE", (2.0, 2.5, 0.0)),
        ("POLAR CUSP", (0.5, 1.2, 2.5)),
        ("TAIL LOBE", (-7.0, 0.0, 4.2)),
        ("PLASMASPHERE", (0.0, -1.8, -1.8))
    ]
    
    for text, loc in labels:
        bpy.ops.object.text_add(location=loc)
        label = bpy.context.active_object
        label.name = f"GEO_Label_{text.replace(' ', '_')}"
        label.data.body = text
        label.rotation_euler = (1.12, 0.0, 0.68)
        label.scale = (0.28, 0.28, 0.28)
        label.data.materials.append(label_mat)
        
        # Hide labels by default
        label.hide_viewport = True
        label.hide_render = True
        
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(label)
                col.objects.link(label)
            except:
                pass

def setup_camera_and_lights():
    """Sets up flat, front-facing camera layout to capture 2D flow perspective."""
    bpy.ops.object.camera_add(location=(0, -22, 0))
    camera = bpy.context.active_object
    camera.name = "SimCamera"
    camera.rotation_euler = (math.pi/2, 0.0, 0.0) # Horizontal side view
    bpy.context.scene.camera = camera
    
    # Strong solar light source positioned on the left (-30, 0, 0) pointing right
    bpy.ops.object.light_add(type='SUN', location=(-30, 0, 0))
    sun = bpy.context.active_object
    sun.name = "SimSun"
    sun.data.energy = 4.5
    sun.rotation_euler = (0, -math.pi/2, 0) # point towards +X

def setup_render_settings():
    """Enables EEVEE render engine and standard animation ranges."""
    try:
        bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        try:
            bpy.context.scene.render.engine = 'BLENDER_EEVEE'
        except TypeError:
            bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 250
    bpy.context.scene.frame_current = 1

def load_and_interpolate_historical_data():
    """Loads preprocessed historical OMNI JSON data."""
    json_path = "E:/Space_Weather_pre/datasets/processed/storm_data_interpolated.json"
    print(f"Loading preprocessed data from: {json_path}")
    if not os.path.exists(json_path):
        print("Warning: Preprocessed storm data file not found. Generating mock values.")
        mock_data = []
        for i in range(250):
            mock_data.append({
                'timestamp': f"05-10 {i//10:02d}:00",
                'VELOCITY': 400.0 + 300.0 * math.sin(i / 40.0),
                'DENSITY': 5.0 + 15.0 * math.sin(i / 30.0),
                'DYNAMIC_PRESSURE': 1.5 + 10.0 * math.sin(i / 35.0),
                'BZ_GSE': 2.0 - 15.0 * math.sin(i / 25.0),
                'KP': 3.0 + 5.0 * math.sin(i / 30.0),
                'DST': -10.0 - 380.0 * math.sin(i / 50.0)
            })
        return mock_data
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def get_spline_point_co(obj, idx):
    """Safely extracts 3D coordinates from a NURBS/Poly spline point."""
    if not obj or not obj.data.splines:
        return None
    spline = obj.data.splines[0]
    pts = spline.points if spline.points else spline.bezier_points
    if not pts or len(pts) == 0:
        return None
    idx = min(max(0, idx), len(pts) - 1)
    co = pts[idx].co
    return (co[0], co[1], co[2])

def real_data_anim_handler(scene):
    """Callback registered with Blender to drive physics simulation parameters frame-by-frame using real OMNI data."""
    global original_spline_points
    col = bpy.data.collections.get(COLLECTION_NAME)
    if not col:
        return
        
    # 1. Retrieve pre-calculated real data
    data_str = scene.get("storm_data", None)
    if not data_str:
        return
        
    try:
        storm_data = json.loads(data_str)
    except:
        return
        
    f_idx = min(max(0, scene.frame_current - 1), 249)
    data = storm_data[f_idx]
    
    velocity = data['VELOCITY']
    pressure = data['DYNAMIC_PRESSURE']
    bz = data['BZ_GSE']
    dst = data['DST']
    kp = data['KP']
    timestamp = data['timestamp']
    
    # Calculate storm factors
    bz_factor = max(0.0, min(1.0, -bz / 15.0)) # 1.0 = highly negative Bz
    storm_intensity = max(0.0, min(1.0, -dst / 350.0))

    # 2. Slowly rotate Earth & Cloud layers
    earth_solid = bpy.data.objects.get("Earth_Solid")
    earth_clouds = bpy.data.objects.get("Earth_Clouds")
    earth_atmos = bpy.data.objects.get("Earth_Atmosphere")
    
    rot_val = scene.frame_current * 0.003
    if earth_solid: earth_solid.rotation_euler.z = rot_val
    if earth_clouds: earth_clouds.rotation_euler.z = rot_val * 1.35
    if earth_atmos: earth_atmos.rotation_euler.z = rot_val

    # 3. Drive Magnetosphere Compression: Standoff distance R_mp proportional to (P_dyn)^-1/6
    pressure_norm = max(0.1, pressure)
    R_shock = max(2.1, min(4.5, 3.5 * ((pressure_norm / 1.5) ** (-1.0/6.0))))
    
    # Scale entire magnetosphere anchor
    anchor = bpy.data.objects.get("Magnetosphere_Anchor")
    if anchor:
        anchor.scale.x = R_shock / 3.5
        
    # Scale Bow Shock Shield and move it to X = -R_shock (left side of scene)
    shield = bpy.data.objects.get("BowShockShield")
    if shield:
        shield.location.x = -R_shock
        # Flex/wiggle the scale slightly to make it look flexible
        time_offset = scene.frame_current * 0.08
        shield.scale.x = 0.65 * (R_shock / 3.5)
        shield.scale.y = 1.2 + 0.04 * math.sin(time_offset * 4.0)
        shield.scale.z = 1.2 + 0.04 * math.cos(time_offset * 4.0)

    # 5. Animate Flexible & "Breakable" Magnetic Field Lines (Alfvén waves + Reconnection)
    time_offset = scene.frame_current * 0.08
    wave_amp = max(0.06, min(0.35, bz_factor * 0.45))
    wave_freq = max(0.4, min(1.8, (velocity / 450.0)))
    
    reconnecting = dst < -150 # Snaps and breaks in tail during intense storms
    recon_x = 4.5 # tail-side reconnection zone
    gap_width = 2.0 * storm_intensity
    
    f_obj = bpy.data.objects.get("FieldLines")
    if f_obj and "FieldLines" in original_spline_points:
        base_splines = original_spline_points["FieldLines"]
        for s_idx, spline in enumerate(f_obj.data.splines):
            if s_idx >= len(base_splines):
                continue
            base_pts = base_splines[s_idx]
            if len(spline.points) != len(base_pts):
                continue
                
            for idx, pt_co in enumerate(base_pts):
                x, y, z, w = pt_co
                
                # Alfvén wave wiggles
                local_amp = wave_amp * (0.4 if x < 0 else 1.6)
                dy = local_amp * math.sin(wave_freq * x - time_offset * 3)
                dz = local_amp * math.cos(wave_freq * x - time_offset * 3)
                
                new_x = x
                new_y = y + dy
                new_z = z + dz
                
                # Day side compression (X < 0)
                if x < 0:
                    new_x = x * (R_shock / 3.5)
                # Night side tail stretch & break (X > 0)
                else:
                    stretch_fac = 1.0 + 0.6 * storm_intensity
                    new_x = x * stretch_fac
                    
                    if reconnecting:
                        dist_to_recon = new_x - recon_x
                        if abs(dist_to_recon) < 2.5:
                            if dist_to_recon > 0:
                                new_x += gap_width * (1.0 - dist_to_recon / 2.5)
                            else:
                                new_x -= gap_width * (1.0 + dist_to_recon / 2.5)
                                
                spline.points[idx].co = (new_x, new_y, new_z, w)

    # 6. Update Magnetosphere & Bow Shock material parameters
    mag_mat = bpy.data.materials.get("MagnetoMat")
    if mag_mat and mag_mat.use_nodes:
        em = mag_mat.node_tree.nodes.get("Emission")
        if em:
            em.inputs['Color'].default_value = (bz_factor, 0.55 * (1.0 - bz_factor), 1.0 - bz_factor * 0.95, 1.0)
            em.inputs['Strength'].default_value = 2.2 + 3.5 * bz_factor

    shock_mat = bpy.data.materials.get("BowShockMat")
    if shock_mat and shock_mat.use_nodes:
        em = shock_mat.node_tree.nodes.get("Emission")
        if em:
            em.inputs['Color'].default_value = (bz_factor, 0.8 * (1.0 - bz_factor), 1.0 - bz_factor * 0.9, 1.0)
            em.inputs['Strength'].default_value = 1.5 + 4.5 * bz_factor
        
        # Scroll texture coordinates to make plasma shimmering flow crawl across shield
        mapping = shock_mat.node_tree.nodes.get("ShockMapping")
        if mapping:
            mapping.inputs['Location'].default_value[0] = -scene.frame_current * 0.16
            mapping.inputs['Location'].default_value[1] = scene.frame_current * 0.05
            
        # Dynamically scale shield opacity based on storm severity (barely visible light)
        mix_nodes = [n for n in shock_mat.node_tree.nodes if n.type == 'MIX_SHADER']
        if mix_nodes:
            mix = mix_nodes[0]
            if mix.inputs[0].is_linked:
                alpha_node = mix.inputs[0].links[0].from_node
                alpha_node.inputs[1].default_value = 0.02 + 0.06 * bz_factor

    # 7. Drive Van Allen Radiation Belts color, scale, and soft opacity based on Dst
    inner_belt = bpy.data.objects.get("VanAllen_Inner")
    outer_belt = bpy.data.objects.get("VanAllen_Outer")
    
    if inner_belt:
        inner_belt.scale = (1.0 + 0.15 * storm_intensity, 1.0 + 0.15 * storm_intensity, 1.0 + 0.05 * storm_intensity)
    if outer_belt:
        outer_belt.scale = (1.0 + 0.35 * storm_intensity, 1.0 + 0.35 * storm_intensity, 1.0 + 0.12 * storm_intensity)
        
    for b_mat_name, base_a in [("VanAllenInnerMat", 0.015), ("VanAllenOuterMat", 0.008)]:
        mat = bpy.data.materials.get(b_mat_name)
        if mat and mat.use_nodes:
            mix_nodes = [n for n in mat.node_tree.nodes if n.type == 'MIX_SHADER']
            if mix_nodes:
                mix = mix_nodes[0]
                if mix.inputs[0].is_linked:
                    alpha_node = mix.inputs[0].links[0].from_node
                    alpha_node.inputs[1].default_value = base_a + base_a * 4.0 * storm_intensity
                    
            em = mat.node_tree.nodes.get("Emission")
            if em:
                em.inputs['Strength'].default_value = 0.8 + 2.5 * storm_intensity

    # 8. Orbit and tumble Debris objects
    debris_objs = [obj for obj in col.objects if obj.name.startswith("Debris_")]
    for d in debris_objs:
        rx, ry, rz = d.get("rot_speed", (0.01, 0.01, 0.01))
        d.rotation_euler.x += rx
        d.rotation_euler.y += ry
        d.rotation_euler.z += rz
        
        r = d.get("orbit_r", 7.5)
        speed = d.get("orbit_speed", 0.008)
        angle = d.get("orbit_angle", 0.0) + speed
        d["orbit_angle"] = angle
        
        d.location.x = r * math.cos(angle)
        d.location.y = r * math.sin(angle)

    # 9. Animate IMF lines wiggling slowly
    imf_lines = [obj for obj in col.objects if obj.name.startswith("SW_IMF_Line_")]
    for line in imf_lines:
        if line.data.splines:
            spline = line.data.splines[0]
            for idx, pt in enumerate(spline.points):
                y_base = pt.co[1]
                pt.co[1] = y_base + 0.015 * math.sin(time_offset * 1.5 + pt.co[0])

    # 10. Animate Solar Wind particles speed (flowing left to right: from -X to +X)
    particles = [obj for obj in col.objects if obj.name.startswith("WindParticle_")]
    p_speed = (velocity / 750.0) * 0.45
    
    for p in particles:
        p["speed"] = p_speed
        offset = p.get("offset_factor", 1.0)
        init_y = p.get("init_y", 0.0)
        init_z = p.get("init_z", 0.0)
        
        p.location.x += p_speed
        
        # Recycle particles once they exit right boundary
        if p.location.x > 15.0:
            p.location.x = -15.0
            p.location.y = random.uniform(-6, 6)
            p.location.z = random.uniform(-6, 6)
            p["init_y"] = p.location.y
            p["init_z"] = p.location.z
            p["offset_factor"] = random.uniform(1.0, 1.35)
            continue
            
        # Deflect particles around bow shock boundary
        x = p.location.x
        if x > -R_shock:
            val = 8.0 * (R_shock + x)
            if val > 0:
                r_boundary = math.sqrt(val)
                target_r = r_boundary * offset
                r_act = math.sqrt(init_y**2 + init_z**2)
                if r_act < target_r:
                    if r_act > 0.001:
                        p.location.y = init_y * (target_r / r_act)
                        p.location.z = init_z * (target_r / r_act)
                    else:
                        p.location.y = target_r
                        p.location.z = 0.0
                else:
                    p.location.y = init_y
                    p.location.z = init_z

    # 11. Animate user modeled particles along their curve trails with gyro-spiral motion
    particles_map = {
        "Proton_A": "Proton_A_Trail",
        "Electron_A": "Electron_A_Trail",
        "Proton_B": "Proton_B_Trail",
        "Proton_C": "Proton_C_Trail",
        "Electron_B": "Electron_B_Trail"
    }
    
    # Set up materials and bevel depth for user objects on frame 1
    if scene.frame_current == 1:
        p_red = bpy.data.materials.get("PartMat_Red") or create_glow_material("PartMat_Red", (1.0, 0.08, 0.08, 1.0), 3.0)
        p_blue = bpy.data.materials.get("PartMat_Blue") or create_glow_material("PartMat_Blue", (0.1, 0.65, 1.0, 1.0), 3.0)
        t_red = bpy.data.materials.get("ProtonTrailMat") or create_glow_material("ProtonTrailMat", (1.0, 0.45, 0.05, 1.0), 1.5)
        t_blue = bpy.data.materials.get("ElectronTrailMat") or create_glow_material("ElectronTrailMat", (0.1, 0.7, 1.0, 1.0), 1.5)
        
        for p_name, t_name in particles_map.items():
            p_obj = bpy.data.objects.get(p_name)
            t_obj = bpy.data.objects.get(t_name)
            
            if p_obj:
                p_obj.data.materials.clear()
                p_obj.data.materials.append(p_red if "Proton" in p_name else p_blue)
            if t_obj:
                t_obj.data.bevel_depth = 0.008
                t_obj.data.bevel_resolution = 2
                t_obj.data.materials.clear()
                t_obj.data.materials.append(t_red if "Proton" in p_name else t_blue)
                
    # Update positions
    for p_name, t_name in particles_map.items():
        p_obj = bpy.data.objects.get(p_name)
        t_obj = bpy.data.objects.get(t_name)
        if p_obj and t_obj:
            co = get_spline_point_co(t_obj, scene.frame_current - 1)
            if co:
                omega = scene.frame_current * 0.75
                r_gyro = 0.07 if "Proton" in p_name else 0.035
                dy = r_gyro * math.sin(omega)
                dz = r_gyro * math.cos(omega)
                p_obj.location = (co[0], co[1] + dy, co[2] + dz)

def generate_scene():
    """Main runner to build the entire space weather data-driven simulation."""
    print("Generating Space Weather Data-Driven Visualizer...")
    
    # 1. Load preprocessed OMNI storm data
    storm_data = load_and_interpolate_historical_data()
    bpy.context.scene["storm_data"] = json.dumps(storm_data)
    
    # 2. Clean spawned objects (leaving user modeling intact)
    clean_previous_sim()
    setup_render_settings()
    setup_space_environment()
    
    # 3. Geometry structures (integrating user Earth & curves)
    build_sun()
    build_earth()
    build_debris()
    build_geo_orbit()
    build_satellite_template()
    instantiate_satellites()
    build_van_allen_belts()
    
    # 4. Fields and dynamic items
    build_magnetosphere()
    build_solar_wind_lines()
    build_bow_shock_shield()
    build_solar_wind_particles()
    
    # 5. Scene elements
    build_status_text()
    build_labels()
    setup_camera_and_lights()
    
    # 6. Register animation pre-handler
    bpy.app.handlers.frame_change_pre.append(real_data_anim_handler)
    print("Data-Driven Space Weather Simulation setup complete!")

if __name__ == "__main__":
    generate_scene()
