import sys
import os

# Import the send_code function from the client script
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from blender_client import send_code

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/change_weather.py [SAFE | MODERATE | SEVERE]")
        sys.exit(1)
        
    state = sys.argv[1].upper()
    if state not in ["SAFE", "MODERATE", "SEVERE"]:
        print("Error: State must be one of SAFE, MODERATE, or SEVERE")
        sys.exit(1)

    # Python code to be executed dynamically in Blender
    code = f"""
import sys
import os
scripts_dir = r"E:\\Space_Weather_pre\\scripts"
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)
    
import build_space_weather_sim
import importlib
importlib.reload(build_space_weather_sim)

# Generate scene for new state
build_space_weather_sim.generate_scene("{state}")

# Align camera and shading in viewport
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.region_3d.view_perspective = 'CAMERA'
                space.shading.type = 'MATERIAL'

# Play the animation loop
try:
    window = bpy.context.window_manager.windows[0]
    area = [a for a in window.screen.areas if a.type == 'VIEW_3D'][0]
    with bpy.context.temp_override(window=window, area=area, screen=window.screen):
        bpy.ops.screen.animation_play()
except Exception:
    pass
"""

    print(f"Sending request to Blender to set space weather state to: {state}...")
    res = send_code(code)
    if res:
        if res.get("error"):
            print("Error updating state inside Blender:", res["error"])
            sys.exit(1)
        else:
            if res.get("stdout"):
                print(res["stdout"], end="")
            print(f"Successfully changed Blender simulation to {state}!")
    else:
        print("Failed to communicate with Blender. Is the server running inside Blender?")
        sys.exit(1)

if __name__ == "__main__":
    main()
