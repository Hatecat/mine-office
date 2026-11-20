# Se ejecuta dentro de Blender: renderiza un .glb desde tres ángulos en una sola imagen.
# blender -b --factory-startup --python vista_blender.py -- modelo.glb salida.png
import bpy, sys, math, mathutils
glb, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ mathutils.Vector(c) for o in objs for c in o.bound_box]
lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
center, size = (lo + hi) / 2, max(hi - lo)
mat = bpy.data.materials.new("arcilla"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.78, 0.74, 0.7, 1)
for o in objs:
    o.data.materials.clear(); o.data.materials.append(mat)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 512, 512
sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.16, 0.17, 0.2)
sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN")); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), 0, math.radians(35)); sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = size * 1.25
import os, tempfile
tiles = []
for i, ang in enumerate((0, 90, 210)):   # frente, lado, tres cuartos por detrás
    a = math.radians(ang); d = size * 3
    # glTF importado: arriba es +Z, el frente mira a -Y
    cam.location = center + mathutils.Vector((math.sin(a) * d, -math.cos(a) * d, size * 0.35))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    p = os.path.join(tempfile.gettempdir(), f"vista_{os.getpid()}_{i}.png"); sc.render.filepath = p
    bpy.ops.render.render(write_still=True); tiles.append(p)
imgs = [bpy.data.images.load(t) for t in tiles]
W = 512 * 3; out_img = bpy.data.images.new("vista", W, 512)
px = [0.0] * (W * 512 * 4)
for k, im in enumerate(imgs):
    src = list(im.pixels)
    for y in range(512):
        row = src[y * 512 * 4:(y + 1) * 512 * 4]
        px[(y * W + k * 512) * 4:(y * W + k * 512 + 512) * 4] = row
out_img.pixels = px; out_img.filepath_raw = out; out_img.file_format = "PNG"; out_img.save()
for t in tiles: os.remove(t)
