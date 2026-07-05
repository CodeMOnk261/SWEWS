import bpy
import math
import random

# Configurations
COLLECTION_NAME = "SpaceWeatherSim"
HOST = '127.0.0.1'
PORT = 19090

def clean_previous_sim():
    """Completely deletes all simulation objects, handlers, and the collection itself."""
    # 1. Unregister frame handler to prevent errors during object deletion
    for h in list(bpy.app.handlers.frame_change_pre):
        if h.__name__ == "solar_wind_anim_handler":
            bpy.app.handlers.frame_change_pre.remove(h)

    # List of prefixes to search and delete
    prefixes = [
        "Earth_Solid", "Earth_Grid", "Earth_Atmosphere", "GEO_Orbit", "GEO_Satellite_", 
        "Satellite_Template", "MagField_", "BowShockShield", 
        "WindParticle_", "StatusHUD", "SimCamera", "SimSun", "Sun_Sphere",
        "Star_", "GEO_Satellite_Bubble_"
    ]
    
    # Delete objects from the collection if it exists
    col = bpy.data.collections.get(COLLECTION_NAME)
    if col:
        for obj in list(col.objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
                
    # Delete any duplicate/orphaned objects in the database matching prefixes
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
                
    # Remove the collection
    if col:
        try:
            bpy.data.collections.remove(col)
        except Exception:
            pass
            
    # Create fresh collection and link
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

def create_space_world_material():
    """Generates a procedural starry world shader with deep purple and blue cosmic nebulae."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new(name="SpaceWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    
    coord = nodes.new(type='ShaderNodeTexCoord')
    
    # Nebula 1 (Deep Purple)
    noise1 = nodes.new(type='ShaderNodeTexNoise')
    noise1.inputs['Scale'].default_value = 1.8
    noise1.inputs['Detail'].default_value = 3.0
    noise1.inputs['Roughness'].default_value = 0.5
    links.new(coord.outputs['Generated'], noise1.inputs['Vector'])
    
    ramp1 = nodes.new(type='ShaderNodeValToRGB')
    ramp1.color_ramp.elements[0].position = 0.35
    ramp1.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp1.color_ramp.elements[1].position = 0.8
    ramp1.color_ramp.elements[1].color = (0.04, 0.005, 0.08, 1.0) # Faint Purple
    links.new(noise1.outputs['Fac'], ramp1.inputs['Fac'])
    
    # Nebula 2 (Deep Cosmic Blue)
    noise2 = nodes.new(type='ShaderNodeTexNoise')
    noise2.inputs['Scale'].default_value = 2.5
    noise2.inputs['Detail'].default_value = 2.0
    links.new(coord.outputs['Generated'], noise2.inputs['Vector'])
    
    ramp2 = nodes.new(type='ShaderNodeValToRGB')
    ramp2.color_ramp.elements[0].position = 0.4
    ramp2.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp2.color_ramp.elements[1].position = 0.85
    ramp2.color_ramp.elements[1].color = (0.0, 0.015, 0.05, 1.0) # Faint Blue
    links.new(noise2.outputs['Fac'], ramp2.inputs['Fac'])
    
    # Combine Nebulae
    mix = nodes.new(type='ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'ADD'
    mix.inputs[0].default_value = 1.0
    links.new(ramp1.outputs['Color'], mix.inputs[1])
    links.new(ramp2.outputs['Color'], mix.inputs[2])
    
    bg = nodes.new(type='ShaderNodeBackground')
    links.new(mix.outputs['Result'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    
    output = nodes.new(type='ShaderNodeOutputWorld')
    links.new(bg.outputs['Background'], output.inputs['Surface'])

def setup_space_environment():
    """Configures the dark space environment, hides grids, and generates stars."""
    # 1. Set up starry world shader
    create_space_world_material()
        
    # 2. Hide grids and axes in viewport
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
                    
    # 3. Generate Starfield (150 tiny glowing stars)
    col = bpy.data.collections.get(COLLECTION_NAME)
    star_mat = create_glow_material("StarMat", color=(1.0, 1.0, 1.0, 1.0), strength=3.0)
    
    for i in range(150):
        theta = random.uniform(0, 2 * math.pi)
        phi = math.acos(random.uniform(-1, 1))
        r = random.uniform(25, 45)
        
        x = r * math.sin(phi) * math.cos(theta)
        y = r * math.sin(phi) * math.sin(theta)
        z = r * math.cos(phi)
        
        bpy.ops.mesh.primitive_ico_sphere_add(radius=0.08, subdivisions=1, location=(x, y, z))
        star = bpy.context.active_object
        star.name = f"Star_{i}"
        star.data.materials.append(star_mat)
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(star)
                col.objects.link(star)
            except:
                pass

def create_procedural_earth_material():
    """Generates a professional-grade procedural Earth material with Day/Night shading and golden city lights."""
    mat = bpy.data.materials.get("EarthMat")
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name="EarthMat")
    mat.use_nodes = True
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    coord = nodes.new(type='ShaderNodeTexCoord')
    
    # 1. Day Side Color (Continents vs Oceans)
    noise_land = nodes.new(type='ShaderNodeTexNoise')
    noise_land.inputs['Scale'].default_value = 3.5
    noise_land.inputs['Detail'].default_value = 8.0
    noise_land.inputs['Roughness'].default_value = 0.65
    links.new(coord.outputs['Generated'], noise_land.inputs['Vector'])
    
    ramp_day = nodes.new(type='ShaderNodeValToRGB')
    ramp_day.color_ramp.elements[0].position = 0.46
    ramp_day.color_ramp.elements[0].color = (0.005, 0.06, 0.22, 1.0) # Deep Shiny Ocean
    ramp_day.color_ramp.elements[1].position = 0.49
    ramp_day.color_ramp.elements[1].color = (0.04, 0.18, 0.05, 1.0) # Forest land
    
    # Desert element
    el = ramp_day.color_ramp.elements.new(0.62)
    el.color = (0.24, 0.20, 0.12, 1.0) # Brown desert
    links.new(noise_land.outputs['Fac'], ramp_day.inputs['Fac'])
    
    # 2. Night Side City Lights (High-frequency voronoi/noise)
    noise_lights = nodes.new(type='ShaderNodeTexNoise')
    noise_lights.inputs['Scale'].default_value = 75.0
    noise_lights.inputs['Detail'].default_value = 6.0
    noise_lights.inputs['Roughness'].default_value = 0.75
    links.new(coord.outputs['Generated'], noise_lights.inputs['Vector'])
    
    ramp_lights = nodes.new(type='ShaderNodeValToRGB')
    ramp_lights.color_ramp.elements[0].position = 0.64
    ramp_lights.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0) # Dark
    ramp_lights.color_ramp.elements[1].position = 0.66
    ramp_lights.color_ramp.elements[1].color = (1.0, 0.75, 0.15, 1.0) # Golden lights
    links.new(noise_lights.outputs['Fac'], ramp_lights.inputs['Fac'])
    
    # 3. Day/Night Boundary Mask (using Normal Vector and Sun Position +X)
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Normal'], sep.inputs['Vector'])
    
    # Map Separated Normal X component [-1, 1] to [0, 1]
    math_mul = nodes.new(type='ShaderNodeMath')
    math_mul.operation = 'MULTIPLY'
    math_mul.inputs[1].default_value = 0.5
    links.new(sep.outputs['X'], math_mul.inputs[0])
    
    math_add = nodes.new(type='ShaderNodeMath')
    math_add.operation = 'ADD'
    math_add.inputs[1].default_value = 0.5
    links.new(math_mul.outputs['Value'], math_add.inputs[0])
    
    ramp_mask = nodes.new(type='ShaderNodeValToRGB')
    ramp_mask.color_ramp.elements[0].position = 0.44
    ramp_mask.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0) # Night
    ramp_mask.color_ramp.elements[1].position = 0.56
    ramp_mask.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0) # Day
    links.new(math_add.outputs['Value'], ramp_mask.inputs['Fac'])
    
    # 4. Night Base Color (Deep dark blue/black)
    mix_night = nodes.new(type='ShaderNodeMix')
    mix_night.data_type = 'RGBA'
    mix_night.blend_type = 'ADD'
    mix_night.inputs[0].default_value = 1.0 # Factor
    mix_night.inputs[6].default_value = (0.002, 0.005, 0.015, 1.0) # Night ocean base (Input A, Color type)
    links.new(ramp_lights.outputs['Color'], mix_night.inputs[7]) # Golden lights (Input B, Color type)
    
    # 5. Blend Day and Night Color
    mix_final = nodes.new(type='ShaderNodeMix')
    mix_final.data_type = 'RGBA'
    mix_final.blend_type = 'MIX'
    links.new(ramp_mask.outputs['Color'], mix_final.inputs[0]) # Factor
    links.new(mix_night.outputs[2], mix_final.inputs[6])      # Night color A (Result index 2 is RGBA)
    links.new(ramp_day.outputs['Color'], mix_final.inputs[7])   # Day color B
    
    # 6. Principled BSDF Setup
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    links.new(mix_final.outputs[2], principled.inputs['Base Color']) # Result index 2 is RGBA
    
    # Shine control (Oceans shiny, land rough)
    ramp_rough = nodes.new(type='ShaderNodeValToRGB')
    ramp_rough.color_ramp.elements[0].position = 0.46
    ramp_rough.color_ramp.elements[0].color = (0.08, 0.08, 0.08, 1.0) # Shiny ocean
    ramp_rough.color_ramp.elements[1].position = 0.49
    ramp_rough.color_ramp.elements[1].color = (0.85, 0.85, 0.85, 1.0) # Matte land
    links.new(noise_land.outputs['Fac'], ramp_rough.inputs['Fac'])
    links.new(ramp_rough.outputs['Color'], principled.inputs['Roughness'])
    
    # City lights emission (Night side only)
    inv_mask = nodes.new(type='ShaderNodeMath')
    inv_mask.operation = 'SUBTRACT'
    inv_mask.inputs[0].default_value = 1.0
    links.new(ramp_mask.outputs['Color'], inv_mask.inputs[1])
    
    mul_emission = nodes.new(type='ShaderNodeMix')
    mul_emission.data_type = 'RGBA'
    mul_emission.blend_type = 'MIX' # Standard MIX is safer
    links.new(inv_mask.outputs['Value'], mul_emission.inputs[0]) # Factor
    mul_emission.inputs[6].default_value = (0.0, 0.0, 0.0, 1.0)  # Input A (black)
    links.new(ramp_lights.outputs['Color'], mul_emission.inputs[7]) # Input B (lights)
    
    if 'Emission Color' in principled.inputs:
        links.new(mul_emission.outputs[2], principled.inputs['Emission Color']) # Result index 2 is RGBA
        principled.inputs['Emission Strength'].default_value = 3.5
    elif 'Emission' in principled.inputs:
        links.new(mul_emission.outputs[2], principled.inputs['Emission'])
        
    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    
    return mat

def create_atmosphere_material():
    """Generates a semi-transparent atmosphere glow material lit by the Sun (+X)."""
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
    
    # 1. Edge Glow (1.0 - Facing^6)
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
    
    # 2. Light Mask (Only illuminated on sunward +X side)
    coord = nodes.new(type='ShaderNodeTexCoord')
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Normal'], sep.inputs['Vector'])
    
    math_mul = nodes.new(type='ShaderNodeMath')
    math_mul.operation = 'MULTIPLY'
    math_mul.inputs[1].default_value = 0.5
    links.new(sep.outputs['X'], math_mul.inputs[0])
    
    math_add = nodes.new(type='ShaderNodeMath')
    math_add.operation = 'ADD'
    math_add.inputs[1].default_value = 0.52 # slight wrap into night side
    links.new(math_mul.outputs['Value'], math_add.inputs[0])
    
    # Final opacity (Edge * Light mask)
    final_alpha = nodes.new(type='ShaderNodeMath')
    final_alpha.operation = 'MULTIPLY'
    links.new(inv.outputs['Value'], final_alpha.inputs[0])
    links.new(math_add.outputs['Value'], final_alpha.inputs[1])
    
    # Emission color
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = (0.25, 0.65, 1.0, 1.0) # Cyan-blue gas
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
    """Generates a semi-transparent, shimmering plasma shockwave front shader."""
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
    
    # Glow colors representing particle deflection heat
    if state == "SEVERE":
        color = (1.0, 0.08, 0.08, 1.0) # Hot Red
        strength = 4.5
    elif state == "MODERATE":
        color = (1.0, 0.5, 0.0, 1.0) # Warm Orange
        strength = 2.8
    else: # SAFE
        color = (0.1, 0.8, 1.0, 1.0) # Calm Cyan
        strength = 1.5
        
    weight = nodes.new(type='ShaderNodeLayerWeight')
    weight.inputs['Blend'].default_value = 0.32
    
    inv = nodes.new(type='ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    links.new(weight.outputs['Facing'], inv.inputs[1])
    
    # Turbulence effect
    coord = nodes.new(type='ShaderNodeTexCoord')
    noise = nodes.new(type='ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 8.5
    noise.inputs['Detail'].default_value = 4.0
    links.new(coord.outputs['Generated'], noise.inputs['Vector'])
    
    mul = nodes.new(type='ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    links.new(inv.outputs['Value'], mul.inputs[0])
    links.new(noise.outputs['Fac'], mul.inputs[1])
    
    alpha = nodes.new(type='ShaderNodeMath')
    alpha.operation = 'MULTIPLY'
    alpha.inputs[1].default_value = 0.25 # max transparency
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

def build_earth():
    """Generates the three-layered hyperrealistic Earth system (Solid, Atmosphere, Grid)."""
    # 1. Inner solid Earth
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.0, location=(0, 0, 0))
    earth_solid = bpy.context.active_object
    earth_solid.name = "Earth_Solid"
    bpy.ops.object.shade_smooth()
    earth_solid.data.materials.append(create_procedural_earth_material())
    
    # 2. Glowing Atmosphere sphere
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.1, location=(0, 0, 0))
    earth_atmos = bpy.context.active_object
    earth_atmos.name = "Earth_Atmosphere"
    bpy.ops.object.shade_smooth()
    earth_atmos.data.materials.append(create_atmosphere_material())
    
    # 3. Analytics Grid (fine prediction grid lines)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.015, location=(0, 0, 0))
    earth_grid = bpy.context.active_object
    earth_grid.name = "Earth_Grid"
    
    wireframe_mod = earth_grid.modifiers.new(name="GridWireframe", type='WIREFRAME')
    wireframe_mod.thickness = 0.004
    wireframe_mod.use_replace = True
    
    grid_color = (0.0, 0.8, 1.0, 0.12) # Very faint overlay
    earth_grid.data.materials.append(create_glow_material("EarthGridMat", color=grid_color, strength=1.0))

def build_sun():
    """Generates the Sun sphere model at +X distance."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=4.5, location=(35, 0, 0))
    sun = bpy.context.active_object
    sun.name = "Sun_Sphere"
    bpy.ops.object.shade_smooth()
    
    sun_color = (1.0, 0.78, 0.2, 1.0)
    sun.data.materials.append(create_glow_material("SunMat", color=sun_color, strength=6.0))

def build_geo_orbit():
    """Generates the glowing Geostationary Orbit ring."""
    bpy.ops.curve.primitive_nurbs_circle_add(radius=7.0, location=(0, 0, 0))
    geo_orbit = bpy.context.active_object
    geo_orbit.name = "GEO_Orbit"
    geo_orbit.data.bevel_depth = 0.02
    geo_orbit.data.bevel_resolution = 2
    
    orbit_color = (0.7, 0.7, 0.0, 1.0)
    geo_orbit.data.materials.append(create_glow_material("OrbitMat", color=orbit_color, strength=1.2))

def build_satellite_template():
    """Generates the Satellite template at the scene origin."""
    if "Satellite_Template" in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects["Satellite_Template"], do_unlink=True)
        
    # 1. Main body
    bpy.ops.mesh.primitive_cube_add(size=0.3, location=(0, 0, 0))
    body = bpy.context.active_object
    body.name = "Satellite_Template"
    body.data.materials.append(create_glow_material("SatBodyMat", color=(0.5, 0.5, 0.6, 1.0), strength=1.5))
    
    # 2. Solar panels
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0.4, 0))
    panel_l = bpy.context.active_object
    panel_l.scale = (0.2, 0.6, 0.02)
    panel_l.data.materials.append(create_glow_material("SatPanelMat", color=(0.0, 0.4, 0.9, 1.0), strength=2.5))
    
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, -0.4, 0))
    panel_r = bpy.context.active_object
    panel_r.scale = (0.2, 0.6, 0.02)
    panel_r.data.materials.append(panel_l.data.materials[0])
    
    # 3. Communications dish
    bpy.ops.mesh.primitive_cone_add(radius1=0.08, depth=0.15, location=(-0.2, 0, 0))
    antenna = bpy.context.active_object
    antenna.rotation_euler = (0, -1.5708, 0)
    antenna.data.materials.append(body.data.materials[0])
    
    # Join them
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    panel_l.select_set(True)
    panel_r.select_set(True)
    antenna.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    
    body.hide_viewport = True
    body.hide_render = True
    return body

def instantiate_satellites(orbit_radius=7.0, num_sats=3, state="SAFE"):
    """Duplicates the satellite template and configures state-based warning indicators."""
    template = bpy.data.objects.get("Satellite_Template")
    if not template:
        return
    col = bpy.data.collections.get(COLLECTION_NAME)
    
    # Warning bubble colors and dimensions based on state
    if state == "SEVERE":
        b_color = (1.0, 0.0, 0.0, 0.25)   # Glowing Red (Dielectric Charging danger)
        b_strength = 3.0
        b_size = 0.65
        show_bubble = True
    elif state == "MODERATE":
        b_color = (1.0, 0.4, 0.0, 0.15)   # Warning Orange
        b_strength = 2.0
        b_size = 0.55
        show_bubble = True
    else: # SAFE
        b_color = (0.0, 0.8, 1.0, 0.05)   # Quiet faint Cyan
        b_strength = 0.5
        b_size = 0.45
        show_bubble = False               # Invisible in Safe mode
        
    bubble_mat = create_glow_material("SatBubbleMat", b_color, b_strength)
    
    for i in range(num_sats):
        angle = (2 * math.pi / num_sats) * i
        x = orbit_radius * math.cos(angle)
        y = orbit_radius * math.sin(angle)
        z = 0.0
        
        # Create satellite
        sat = template.copy()
        sat.name = f"GEO_Satellite_{i+1}"
        sat.location = (x, y, z)
        sat.rotation_euler = (0, 0, angle)
        sat.hide_viewport = False
        sat.hide_render = False
        
        if col:
            col.objects.link(sat)
            
        # Create satellite warning shield bubble
        bpy.ops.mesh.primitive_uv_sphere_add(radius=b_size, location=(x, y, z))
        bubble = bpy.context.active_object
        bubble.name = f"GEO_Satellite_Bubble_{i+1}"
        bubble.display_type = 'WIRE'  # Holographic cage style
        bubble.data.materials.append(bubble_mat)
        
        if not show_bubble:
            bubble.hide_viewport = True
            bubble.hide_render = True
            
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(bubble)
                col.objects.link(bubble)
            except:
                pass

def build_magnetosphere(state="SAFE"):
    """Generates the 3D magnetic field cage around Earth with solar wind distortions."""
    # State parameter adjustments
    if state == "SEVERE":
        color = (1.0, 0.1, 0.1, 1.0)
        strength = 4.5
        day_compress = 0.42
        night_elongate = 2.3
        shift_x = -0.9
    elif state == "MODERATE":
        color = (1.0, 0.5, 0.0, 1.0)
        strength = 3.0
        day_compress = 0.52
        night_elongate = 1.95
        shift_x = -0.6
    else: # SAFE
        color = (0.0, 0.85, 1.0, 1.0)
        strength = 2.0
        day_compress = 0.65
        night_elongate = 1.6
        shift_x = -0.3
        
    shells = [4.0, 5.5]
    planes = 8
    col = bpy.data.collections.get(COLLECTION_NAME)
    
    for s_idx, R_0 in enumerate(shells):
        for p_idx in range(planes):
            phi = (2 * math.pi / planes) * p_idx
            points = []
            steps = 36
            for i in range(steps + 1):
                theta = 0.08 + (math.pi - 0.16) * (i / steps)
                r = R_0 * (math.sin(theta) ** 2)
                
                x = r * math.sin(theta) * math.cos(phi)
                y = r * math.sin(theta) * math.sin(phi)
                z = r * math.cos(theta)
                
                # Compress day-side (+X) and stretch night-side (-X)
                if x > 0:
                    x *= day_compress
                    y *= (day_compress + 0.1)
                else:
                    x *= night_elongate
                    y *= 1.2
                    
                x += shift_x
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
            else:
                bpy.context.scene.collection.objects.link(obj)
            
            obj.data.bevel_depth = 0.015
            obj.data.bevel_resolution = 2
            obj.data.materials.append(create_glow_material(f"MagMat_{name}", color, strength))

def build_bow_shock_shield(state="SAFE"):
    """Creates a visible, shimmering plasma bow shock wave front."""
    if state == "SEVERE":
        shield_x = 2.3
        shield_scale = (0.45, 1.4, 1.4)
    elif state == "MODERATE":
        shield_x = 2.9
        shield_scale = (0.55, 1.3, 1.3)
    else: # SAFE
        shield_x = 3.5
        shield_scale = (0.65, 1.2, 1.2)
        
    bpy.ops.mesh.primitive_uv_sphere_add(radius=3.5, location=(shield_x, 0, 0))
    shield = bpy.context.active_object
    shield.name = "BowShockShield"
    shield.scale = shield_scale
    
    # Collision properties
    collision_mod = shield.modifiers.new(name="ShieldCollision", type='COLLISION')
    collision_mod.settings.damping_factor = 0.3
    collision_mod.settings.friction_factor = 0.05
    collision_mod.settings.permeability = 0.0
    
    # Assign glowing shimmering bow shock material
    shield.data.materials.append(create_bow_shock_material(state))
    bpy.ops.object.shade_smooth()

def build_solar_wind_particles(state="SAFE"):
    """Creates individual solar wind particle spheres that will be animated procedurally."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    
    # State-based properties
    if state == "SEVERE":
        p_count = 60
        speed = 0.55
        p_color = (1.0, 0.1, 0.1, 1.0)
        strength = 4.0
        size = 0.12
    elif state == "MODERATE":
        p_count = 40
        speed = 0.38
        p_color = (1.0, 0.55, 0.0, 1.0)
        strength = 3.0
        size = 0.1
    else: # SAFE
        p_count = 25
        speed = 0.22
        p_color = (0.1, 1.0, 0.4, 1.0)
        strength = 2.0
        size = 0.08
        
    p_mat = create_glow_material("ParticleGlowMat", p_color, strength)
    
    for i in range(p_count):
        # Build particle icosphere
        bpy.ops.mesh.primitive_ico_sphere_add(radius=size, subdivisions=1)
        p = bpy.context.active_object
        p.name = f"WindParticle_{i}"
        p.data.materials.append(p_mat)
        
        # Set custom properties
        p.location.x = random.uniform(-15, 15)
        p.location.y = random.uniform(-6, 6)
        p.location.z = random.uniform(-6, 6)
        
        p["speed"] = speed
        p["offset_factor"] = random.uniform(1.0, 1.35)
        p["init_y"] = p.location.y
        p["init_z"] = p.location.z
        
        if col:
            try:
                bpy.context.scene.collection.objects.unlink(p)
                col.objects.link(p)
            except:
                pass

def solar_wind_anim_handler(scene):
    """Callback registered with Blender to rotate Earth and animate particle deflection on frame changes."""
    col = bpy.data.collections.get(COLLECTION_NAME)
    if not col:
        return
        
    # 1. Rotate Earth layers
    earth_atmos = bpy.data.objects.get("Earth_Atmosphere")
    earth_grid = bpy.data.objects.get("Earth_Grid")
    earth_solid = bpy.data.objects.get("Earth_Solid")
    
    rotation_speed = scene.frame_current * 0.005
    if earth_atmos:
        earth_atmos.rotation_euler.z = rotation_speed
    if earth_grid:
        earth_grid.rotation_euler.z = rotation_speed
    if earth_solid:
        earth_solid.rotation_euler.z = rotation_speed
        
    # 2. Animate Solar Wind deflection
    particles = [obj for obj in col.objects if obj.name.startswith("WindParticle_")]
    shield = bpy.data.objects.get("BowShockShield")
    
    X_shock = shield.location.x if shield else 3.5
    R = 4.0 # Shock curvature constant
    
    for p in particles:
        speed = p.get("speed", 0.25)
        offset = p.get("offset_factor", 1.0)
        init_y = p.get("init_y", 0.0)
        init_z = p.get("init_z", 0.0)
        
        # Step particles to the left (-X)
        p.location.x -= speed
        
        # Recycle particle when off-screen
        if p.location.x < -15.0:
            p.location.x = 15.0
            p.location.y = random.uniform(-6, 6)
            p.location.z = random.uniform(-6, 6)
            p["init_y"] = p.location.y
            p["init_z"] = p.location.z
            p["offset_factor"] = random.uniform(1.0, 1.35)
            continue
            
        # Deflect around bow shock paraboloid
        x = p.location.x
        if x < X_shock:
            val = 2 * R * (X_shock - x)
            if val > 0:
                r_boundary = math.sqrt(val)
                target_r = r_boundary * offset
                
                # Check initial position radius
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
            else:
                p.location.y = init_y
                p.location.z = init_z
        else:
            p.location.y = init_y
            p.location.z = init_z

def build_status_text(state="SAFE"):
    """Creates a floating HUD-like status text indicating warning status."""
    if state == "SEVERE":
        text_str = "SPACE WEATHER: CRITICAL STORM"
        color = (1.0, 0.0, 0.0, 1.0)
    elif state == "MODERATE":
        text_str = "SPACE WEATHER: MODERATE ALERT"
        color = (1.0, 0.5, 0.0, 1.0)
    else:
        text_str = "SPACE WEATHER: SAFE (QUIET)"
        color = (0.0, 1.0, 0.5, 1.0)
        
    bpy.ops.object.text_add(location=(-5, -3, 6))
    text_obj = bpy.context.active_object
    text_obj.name = "StatusHUD"
    text_obj.data.body = text_str
    
    text_obj.rotation_euler = (1.12, 0.0, 0.68)
    text_obj.scale = (0.55, 0.55, 0.55)
    text_obj.data.materials.append(create_glow_material("HUDTextMat", color, strength=3.0))

def setup_camera_and_lights():
    """Sets up the operational camera and basic scene light."""
    # Active Camera
    bpy.ops.object.camera_add(location=(14, -18, 9))
    camera = bpy.context.active_object
    camera.name = "SimCamera"
    camera.rotation_euler = (1.12, 0.0, 0.68)
    bpy.context.scene.camera = camera
    
    # Sun lighting
    bpy.ops.object.light_add(type='SUN', location=(35, 0, 0))
    sun = bpy.context.active_object
    sun.name = "SimSun"
    sun.data.energy = 3.5
    sun.rotation_euler = (0, 1.5708, 0) # Shine from +X directly

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

def generate_scene(state="SAFE"):
    """Main runner to build the entire simulation for a given space weather state."""
    print(f"Generating Space Weather Simulation: State = {state}")
    
    # 1. Clean scene
    clean_previous_sim()
    setup_render_settings()
    
    # 2. Environment setups
    setup_space_environment()
    
    # 3. Geometry structures
    build_sun()
    build_earth()
    build_geo_orbit()
    build_satellite_template()
    instantiate_satellites(state=state)
    
    # 4. Physics and dynamic items
    build_magnetosphere(state=state)
    build_bow_shock_shield(state=state)
    build_solar_wind_particles(state=state)
    
    # 5. Scene elements
    build_status_text(state=state)
    setup_camera_and_lights()
    
    # 6. Register animation logic callback
    bpy.app.handlers.frame_change_pre.append(solar_wind_anim_handler)
    print("Space Weather Simulation generation complete!")

if __name__ == "__main__":
    generate_scene("SAFE")
