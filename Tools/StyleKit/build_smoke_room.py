"""Builds the stand room (style inspired by The Finals) around the Smoke stand.

Run in the editor: File > Execute Python Script... > Tools/StyleKit/build_smoke_room.py
Safe to run again: everything it spawned is tagged "StyleKit" and rebuilt from scratch.

What it does:
  1. Generates the kit meshes (meshgen.py) into DCC/ and imports them to /Game/Style/Meshes
  2. Creates M_Style_Surface (lit, HLSL smudge for roughness) and M_Style_Light (unlit emissive)
     plus material instances in the project palette
  3. Opens /Game/Maps/Smoke, removes the old backdrop setup and spawns the room, lights, camera
"""

import math
import os
import sys

import unreal

PROJECT_DIR = os.path.abspath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
REPO_DIR = os.path.dirname(PROJECT_DIR)
KIT_DIR = os.path.join(REPO_DIR, "Tools", "StyleKit")
DCC_DIR = os.path.join(REPO_DIR, "DCC")
if KIT_DIR not in sys.path:
    sys.path.insert(0, KIT_DIR)
import meshgen  # noqa: E402
import importlib  # noqa: E402
importlib.reload(meshgen)

MAT_DIR = "/Game/Style/Materials"
MESH_DIR = "/Game/Style/Meshes"
BP_DIR = "/Game/Style/Blueprints"
MAP = "/Game/Maps/Smoke"
TAG = "StyleKit"

# palette (sRGB hex)
ACCENT = "2096F3"
DARK_1 = "1A1A1A"
DARK_2 = "222222"
GREY = "626262"
LIGHT = "F4F7FF"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
# editor subsystems are missing in headless (commandlet) runs: fall back to the old library
actors_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem) or unreal.EditorLevelLibrary


def log(msg):
    unreal.log("[StyleKit] " + msg)


def srgb(hex_str, alpha=1.0):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
    return unreal.LinearColor(lin(r), lin(g), lin(b), alpha)


def color8(hex_str):
    r, g, b = (int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
    return unreal.Color(r=r, g=g, b=b, a=255)


# ------------------------------------------------------------------ materials

SMUDGE_HLSL = """
// 3 octaves of value noise in world space: soft smudges for roughness
float3 p = WorldPos * Scale;
float total = 0.0;
float amp = 0.5;
const float3 K = float3(127.1, 311.7, 74.7);
for (int o = 0; o < 3; o++)
{
    float3 i = floor(p);
    float3 f = frac(p);
    float3 u = f * f * (3.0 - 2.0 * f);
    float4 h0 = frac(sin(float4(dot(i, K), dot(i + float3(1, 0, 0), K),
                                dot(i + float3(0, 1, 0), K), dot(i + float3(1, 1, 0), K))) * 43758.5453);
    float4 h1 = frac(sin(float4(dot(i + float3(0, 0, 1), K), dot(i + float3(1, 0, 1), K),
                                dot(i + float3(0, 1, 1), K), dot(i + float3(1, 1, 1), K))) * 43758.5453);
    float4 z = lerp(h0, h1, u.z);
    float2 y = lerp(z.xy, z.zw, u.y);
    total += amp * lerp(y.x, y.y, u.x);
    p = p * 2.03 + 17.0;
    amp *= 0.5;
}
return saturate((total / 0.875 - 0.3) * 1.6);
"""


def fresh_asset(name, path, cls, factory):
    full = path + "/" + name
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    return asset_tools.create_asset(name, path, cls, factory)


def scalar(mat, name, value, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", value)
    return e


def vector(mat, name, value, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", value)
    return e


def build_surface_material():
    m = fresh_asset("M_Style_Surface", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    color = vector(m, "Color", srgb(GREY), -900, -300)
    metallic = scalar(m, "Metallic", 0.0, -900, -150)
    specular = scalar(m, "Specular", 0.5, -900, -60)
    rough = scalar(m, "Roughness", 0.3, -900, 40)
    smudge_amt = scalar(m, "SmudgeAmount", 0.15, -900, 130)
    smudge_scale = scalar(m, "SmudgeScale", 0.006, -1300, 330)
    wpos = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -1300, 230)

    custom = mel.create_material_expression(m, unreal.MaterialExpressionCustom, -1000, 250)
    custom.set_editor_property("code", SMUDGE_HLSL)
    custom.set_editor_property("description", "Smudge")
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    inp_pos = unreal.CustomInput()
    inp_pos.set_editor_property("input_name", "WorldPos")
    inp_scale = unreal.CustomInput()
    inp_scale.set_editor_property("input_name", "Scale")
    custom.set_editor_property("inputs", [inp_pos, inp_scale])
    mel.connect_material_expressions(wpos, "", custom, "WorldPos")
    mel.connect_material_expressions(smudge_scale, "", custom, "Scale")

    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -650, 160)
    mel.connect_material_expressions(custom, "", mul, "A")
    mel.connect_material_expressions(smudge_amt, "", mul, "B")
    add = mel.create_material_expression(m, unreal.MaterialExpressionAdd, -450, 60)
    mel.connect_material_expressions(rough, "", add, "A")
    mel.connect_material_expressions(mul, "", add, "B")

    emissive = vector(m, "Emissive", unreal.LinearColor(0, 0, 0, 1), -900, 420)
    em_strength = scalar(m, "EmissiveStrength", 0.0, -900, 560)
    em_mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -600, 460)
    mel.connect_material_expressions(emissive, "", em_mul, "A")
    mel.connect_material_expressions(em_strength, "", em_mul, "B")

    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(add, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(em_mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    return m


def build_light_material():
    m = fresh_asset("M_Style_Light", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    color = vector(m, "Color", srgb(LIGHT), -600, -100)
    strength = scalar(m, "Strength", 4.0, -600, 60)
    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -300, 0)
    mel.connect_material_expressions(color, "", mul, "A")
    mel.connect_material_expressions(strength, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    return m


def instance(name, parent, vectors=None, scalars=None):
    mi = fresh_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, v)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    mel.update_material_instance(mi)
    return mi


def build_materials():
    surf = build_surface_material()
    light = build_light_material()
    return {
        # glossy black floor with patchy reflections
        "Floor": instance("MI_Style_Floor", surf, {"Color": srgb(DARK_1)},
                          {"Roughness": 0.06, "SmudgeAmount": 0.22, "SmudgeScale": 0.004}),
        "Wall": instance("MI_Style_Wall", surf, {"Color": srgb(GREY)},
                         {"Roughness": 0.25, "SmudgeAmount": 0.18, "SmudgeScale": 0.005}),
        "AccentGloss": instance("MI_Style_AccentGloss", surf, {"Color": srgb(ACCENT)},
                                {"Roughness": 0.12, "SmudgeAmount": 0.1, "Specular": 0.6}),
        "Trim": instance("MI_Style_Trim", surf, {"Color": srgb(DARK_1)},
                         {"Roughness": 0.14, "SmudgeAmount": 0.08}),
        "Panel": instance("MI_Style_Panel", surf, {"Color": srgb(DARK_2)},
                          {"Roughness": 0.4, "SmudgeAmount": 0.12}),
        # matte near-black backdrop inside the booth: the effect has to read against it
        "Void": instance("MI_Style_Void", surf, {"Color": srgb(DARK_1)},
                         {"Roughness": 0.75, "SmudgeAmount": 0.0, "Specular": 0.3}),
        "LightWhite": instance("MI_Style_LightWhite", light, {"Color": srgb(LIGHT)}, {"Strength": 3.0}),
        "LightAccent": instance("MI_Style_LightAccent", light, {"Color": srgb(ACCENT)}, {"Strength": 10.0}),
        "LightAccentSoft": instance("MI_Style_LightAccentSoft", light, {"Color": srgb(ACCENT)}, {"Strength": 3.0}),
        "StageTop": build_stage_top_material(),
    }


STAGE_HLSL = """
// Stage top markings in object space (cm): rings, dashed axes with a 10 cm ruler,
// outer frame and accent corner brackets. Antialiased with fwidth, no textures.
float2 p = P.xy;
float2 ap = abs(p);
float aa = max(fwidth(p.x), fwidth(p.y)) * 1.2 + 1e-4;
float hw = Width * 0.5;
float r = length(p);
#define LINE(d, w) (1.0 - smoothstep((w), (w) + aa, (d)))

float grey = 0.0;
float acc = 0.0;

// rings: 1 m and 1.5 m grey, 0.5 m accent
grey = max(grey, LINE(min(abs(r - 100.0), abs(r - 150.0)), hw));
acc = max(acc, LINE(abs(r - 50.0), Width));

// dashed axes from the inner ring to the frame
float dashX = step(frac(ap.x / 30.0), 0.62);
float dashY = step(frac(ap.y / 30.0), 0.62);
grey = max(grey, LINE(ap.y, hw) * step(62.0, ap.x) * step(ap.x, Extent - 8.0) * dashX);
grey = max(grey, LINE(ap.x, hw) * step(62.0, ap.y) * step(ap.y, Extent - 8.0) * dashY);

// ruler ticks along both axes: every 10 cm, longer every 50 cm
float tx = abs(frac(ap.x / 10.0 + 0.5) - 0.5) * 10.0;
float ty = abs(frac(ap.y / 10.0 + 0.5) - 0.5) * 10.0;
float mx = step(abs(frac(ap.x / 50.0 + 0.5) - 0.5) * 50.0, 1.0);
float my = step(abs(frac(ap.y / 50.0 + 0.5) - 0.5) * 50.0, 1.0);
grey = max(grey, LINE(tx, hw) * step(ap.y, lerp(4.0, 11.0, mx)) * step(55.0, ap.x) * step(ap.x, Extent - 8.0));
grey = max(grey, LINE(ty, hw) * step(ap.x, lerp(4.0, 11.0, my)) * step(55.0, ap.y) * step(ap.y, Extent - 8.0));

// outer frame and accent corner brackets
grey = max(grey, LINE(abs(max(ap.x, ap.y) - Extent), hw));
acc = max(acc, LINE(abs(max(ap.x, ap.y) - (Extent - 12.0)), Width) * step(Extent - 60.0, min(ap.x, ap.y)));

return float2(grey, acc);
"""


def build_stage_top_material():
    m = fresh_asset("M_Style_StageTop", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    base = vector(m, "Base", srgb(DARK_2), -500, -400)
    line = vector(m, "Line", srgb(GREY), -500, -250)
    accent = vector(m, "Accent", srgb(ACCENT), -500, -100)
    width = scalar(m, "Width", 1.6, -1300, 260)
    extent = scalar(m, "Extent", 178.0, -1300, 360)
    glow = scalar(m, "AccentGlow", 2.5, -500, 450)
    rough = scalar(m, "Roughness", 0.3, -500, 300)

    wpos = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -1500, 60)
    opos = mel.create_material_expression(m, unreal.MaterialExpressionObjectPositionWS, -1500, 160)
    local = mel.create_material_expression(m, unreal.MaterialExpressionSubtract, -1300, 100)
    mel.connect_material_expressions(wpos, "", local, "A")
    mel.connect_material_expressions(opos, "", local, "B")

    custom = mel.create_material_expression(m, unreal.MaterialExpressionCustom, -1050, 150)
    custom.set_editor_property("code", STAGE_HLSL)
    custom.set_editor_property("description", "StageMarkings")
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    ins = []
    for n in ("P", "Width", "Extent"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    custom.set_editor_property("inputs", ins)
    mel.connect_material_expressions(local, "", custom, "P")
    mel.connect_material_expressions(width, "", custom, "Width")
    mel.connect_material_expressions(extent, "", custom, "Extent")

    def mask(r, g, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionComponentMask, -800, y)
        e.set_editor_property("r", r)
        e.set_editor_property("g", g)
        mel.connect_material_expressions(custom, "", e, "")
        return e

    grey_mask = mask(True, False, 100)
    acc_mask = mask(False, True, 220)

    lerp1 = mel.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -250, -300)
    mel.connect_material_expressions(base, "", lerp1, "A")
    mel.connect_material_expressions(line, "", lerp1, "B")
    mel.connect_material_expressions(grey_mask, "", lerp1, "Alpha")
    lerp2 = mel.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -50, -200)
    mel.connect_material_expressions(lerp1, "", lerp2, "A")
    mel.connect_material_expressions(accent, "", lerp2, "B")
    mel.connect_material_expressions(acc_mask, "", lerp2, "Alpha")

    em1 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 300)
    mel.connect_material_expressions(accent, "", em1, "A")
    mel.connect_material_expressions(acc_mask, "", em1, "B")
    em2 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -50, 350)
    mel.connect_material_expressions(em1, "", em2, "A")
    mel.connect_material_expressions(glow, "", em2, "B")

    mel.connect_material_property(lerp2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(em2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    return m


# ------------------------------------------------------------------ meshes

SLOTS = {
    "SM_Style_RoomShell": {"Floor": "Floor", "Wall": "Wall"},
    "SM_Style_Booth": {"Frame": "AccentGloss", "Back": "Void"},
    "SM_Style_Stage": {"Body": "Trim", "Glow": "LightAccent", "Top": "StageTop"},
    "SM_Style_Pedestal": {"Ring": "AccentGloss", "Body": "Trim", "Glow": "LightAccentSoft"},
    "SM_Style_CeilingLight": {"Frame": "Trim", "Panel": "LightWhite"},
    "SM_Style_CeilingBar": {"Frame": "Trim", "Panel": "LightWhite"},
    "SM_Style_Crate": {"Surface": "Panel"},
    "SM_Style_Banner": {"Surface": "AccentGloss"},
    "SM_Style_Strip": {"Surface": "LightAccent"},
}


def import_meshes(mats):
    meshgen.write_all(DCC_DIR)
    tasks = []
    for name in SLOTS:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", os.path.join(DCC_DIR, name + ".obj"))
        t.set_editor_property("destination_path", MESH_DIR)
        t.set_editor_property("destination_name", name)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tasks.append(t)
    asset_tools.import_asset_tasks(tasks)

    sm_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    meshes = {}
    for name, slot_map in SLOTS.items():
        mesh = unreal.load_asset(MESH_DIR + "/" + name)
        if mesh is None:
            raise RuntimeError("Import failed: " + name)
        statics = mesh.get_editor_property("static_materials")
        for i, sm in enumerate(statics):
            slot = str(sm.get_editor_property("material_slot_name"))
            key = next((v for k, v in slot_map.items() if k.lower() in slot.lower()), None)
            if key is None and len(slot_map) == 1:
                key = list(slot_map.values())[0]
            if key:
                mesh.set_material(i, mats[key])
            log("%s slot %d '%s' -> %s" % (name, i, slot, key))
        # low-poly kit: plain meshes are cheaper than Nanite here and give exact complex collision
        ns = mesh.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", ns)
        # walkable: collide against the render mesh itself (the inward room shell has no convex hull)
        body = mesh.get_editor_property("body_setup")
        if body is not None:
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        else:
            unreal.log_warning("[StyleKit] %s has no body setup" % name)
        lib = sm_sub if sm_sub is not None else unreal.EditorStaticMeshLibrary
        bs = lib.get_lod_build_settings(mesh, 0)
        # inward-facing shell: a one-sided distance field would read the whole room as "inside"
        bs.set_editor_property("generate_distance_field_as_if_two_sided", name == "SM_Style_RoomShell")
        lib.set_lod_build_settings(mesh, 0, bs)  # also rebuilds the mesh with the settings above
        log("%s bounds %s" % (name, mesh.get_bounding_box()))
        meshes[name] = mesh

    # importers may create placeholder materials next to the meshes: remove them
    for path in eal.list_assets(MESH_DIR, recursive=False):
        data = eal.find_asset_data(path)
        cls = str(data.asset_class_path.asset_name)
        if cls in ("Material", "MaterialInstanceConstant"):
            log("removing importer material " + path)
            eal.delete_asset(path)
    return meshes


# ------------------------------------------------------------------ game mode

GAME_MODE = "/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode"


def build_game_mode():
    """Walkable stand: the stock Third Person template character (content copied from the engine templates)."""
    old = BP_DIR + "/BP_StandGameMode"
    if eal.does_asset_exist(old):
        eal.delete_asset(old)
    if not eal.does_asset_exist(GAME_MODE):
        raise RuntimeError("Third Person content missing: copy it into Content/ThirdPerson, Characters, Input")
    return eal.load_blueprint_class(GAME_MODE)


# ------------------------------------------------------------------ level

def rot_to(src, dst):
    d = (dst[0] - src[0], dst[1] - src[1], dst[2] - src[2])
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)


def tag(actor, label):
    actor.set_actor_label(label)
    actor.set_folder_path(TAG)
    actor.tags = [TAG]
    return actor


def mesh_actor(mesh, label, loc, yaw=0.0, scale=(1, 1, 1), material=None):
    a = actors_sub.spawn_actor_from_object(mesh, unreal.Vector(*loc), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(*scale))
    comp = a.static_mesh_component
    if material is not None:
        comp.set_material(0, material)
    return tag(a, label)


def text_actor(label, text, loc, yaw, size, color_hex, align_left=False):
    a = actors_sub.spawn_actor_from_class(unreal.TextRenderActor, unreal.Vector(*loc),
                                          unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    c = a.text_render
    c.set_editor_property("text", text)
    c.set_editor_property("world_size", size)
    c.set_editor_property("text_render_color", color8(color_hex))
    c.set_editor_property("horizontal_alignment",
                          unreal.HorizTextAligment.EHTA_LEFT if align_left else unreal.HorizTextAligment.EHTA_CENTER)
    c.set_editor_property("vertical_alignment", unreal.VerticalTextAligment.EVRTA_TEXT_CENTER)
    return tag(a, label)


def rect_light(label, loc, rot, width, height, intensity, color_hex, attenuation, barn=88.0, barn_length=30.0,
               shadows=True):
    a = actors_sub.spawn_actor_from_class(unreal.RectLight, unreal.Vector(*loc), rot)
    c = a.rect_light_component
    c.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    c.set_editor_property("intensity", intensity)
    c.set_editor_property("source_width", width)
    c.set_editor_property("source_height", height)
    c.set_editor_property("barn_door_angle", barn)
    c.set_editor_property("barn_door_length", barn_length)
    c.set_editor_property("attenuation_radius", attenuation)
    c.set_editor_property("light_color", color8(color_hex))
    c.set_editor_property("cast_shadows", shadows)
    return tag(a, label)


def build_level(meshes, mats, game_mode):
    unreal.EditorLoadingAndSavingUtils.load_map(MAP)

    legacy = {"Backdrop", "Sun", "Cube", "Wall", "Vent", "VentRing", "Platform", "Label"}
    for a in actors_sub.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label() in legacy:
            actors_sub.destroy_actor(a)

    by_label = {a.get_actor_label(): a for a in actors_sub.get_all_level_actors()}
    floor_z = meshgen.ROOM["z0"]
    back_x = meshgen.ROOM["x1"]
    wall_y = meshgen.ROOM["y"]

    # Layout: the stand sits at the room center (0, 0). Everything is mirrored across Y=0;
    # along X the booth closes the +X end and the player starts at the -X end.
    front_x = meshgen.ROOM["x0"]
    ceil = meshgen.ROOM["z1"]
    half_stage = meshgen.STAGE["size"] / 2.0
    down = unreal.Rotator(roll=0, pitch=-90, yaw=0)

    # shell, central stage with the vent pedestal, booth on the +X wall
    mesh_actor(meshes["SM_Style_RoomShell"], "Room", (0, 0, 0))
    mesh_actor(meshes["SM_Style_Stage"], "Stage", (0, 0, floor_z))
    mesh_actor(meshes["SM_Style_Pedestal"], "Pedestal", (0, 0, 0))
    mesh_actor(meshes["SM_Style_Booth"], "Booth", (back_x, 0, floor_z))
    text_actor("StageLabel", "01 / SMOKE", (-half_stage - 0.5, 0, floor_z + 10), 180, 12, ACCENT)

    # lamp bar under the inner top of the booth + its light (frame 42 cm; open part in front of the back panel)
    booth_top = floor_z + 480 - 42
    booth_open_x = back_x - meshgen.BOOTH["back"] - meshgen.BOOTH["open_depth"] / 2.0
    booth_front_x = back_x - meshgen.BOOTH["back"] - meshgen.BOOTH["open_depth"]
    mesh_actor(meshes["SM_Style_Strip"], "BoothLamp", (booth_open_x, 0, booth_top - 9),
               scale=(0.3, 2.8, 0.05), material=mats["LightWhite"])
    rect_light("BoothLight", (booth_open_x, 0, booth_top - 12), down, 280, 30, 40.0, LIGHT, 700)

    # ceiling: big coffer over the stage, two light bars mirrored along X.
    # No barn doors, and the rect lights sit inside the recess (just under the panel), so their
    # hemisphere cut-off lands at the ceiling instead of drawing a hard edge across the coves.
    # Emissive panels stay out of the Lumen scene: its low-res surface cache drew blocky
    # reflections on the glossy floor; the rect lights give the correctly shaped highlights.
    def lamp(mesh, label, x):
        a = mesh_actor(meshes[mesh], label, (x, 0, ceil))
        a.static_mesh_component.set_editor_property("affect_dynamic_indirect_lighting", False)
        return a

    lamp("SM_Style_CeilingLight", "CeilingLight", 0.0)
    rect_light("CeilingRect", (0, 0, ceil - 6), down, 620, 580, 380.0, LIGHT, 2600, barn=88.0, barn_length=0.0)
    # The ceiling lights only emit downwards and the black floor bounces little, so the ceiling and
    # the upper coves fell to black with a hard edge at the lamp height. A wide, shadowless rect light
    # facing up fills them softly (cheap: no shadows, no specular on the floor).
    rect_light("CeilingFill", (0, 0, 250), unreal.Rotator(roll=0, pitch=90, yaw=0), 1400, 1100, 130.0, LIGHT, 1600,
               barn=88.0, barn_length=0.0, shadows=False)
    for side, x in (("Front", -560.0), ("Back", 560.0)):
        lamp("SM_Style_CeilingBar", "CeilingBar" + side, x)
        rect_light("CeilingBarRect" + side, (x, 0, ceil - 6), down, 130, 500, 140.0, LIGHT, 2000, barn=88.0, barn_length=0.0)

    # side walls: identical accent banners centered on X=0 (left faces +Y, right faces -Y)
    banner_z = 70
    for side, sign, yaw in (("L", -1.0, 90.0), ("R", 1.0, -90.0)):
        y_face = sign * (wall_y - 16.5)
        mesh_actor(meshes["SM_Style_Banner"], "Banner" + side, (0, sign * (wall_y - 8), banner_z))
        text_actor("BannerTitle" + side, "SMOKE", (0, y_face, banner_z + 132), yaw, 200, DARK_1)
        text_actor("BannerSub" + side, "01 / VFX STAND / NIAGARA", (0, y_face, banner_z + 38), yaw, 24, DARK_1)
        mesh_actor(meshes["SM_Style_Strip"], "WallLine" + side, (0, sign * (wall_y - 3), 360), scale=(12.0, 0.06, 0.05))

    # front wall (player side): short banner with the project name, centered
    mesh_actor(meshes["SM_Style_Banner"], "BannerFront", (front_x + 8, 0, 150), yaw=90, scale=(0.55, 1.0, 0.5))
    text_actor("BannerFrontTitle", "PORTFOLIO-UE5", (front_x + 16.5, 0, 207), 0, 70, DARK_1)

    # floor guide lines on the X axis: from the front wall to the stage, from the stage to the booth
    stage_edge = half_stage + 30.0
    for label, x0, x1 in (("FloorLineFront", front_x + 120.0, -stage_edge), ("FloorLineBack", stage_edge, booth_front_x - 40.0)):
        mesh_actor(meshes["SM_Style_Strip"], label, ((x0 + x1) / 2.0, 0, floor_z), scale=((x1 - x0) / 100.0, 0.06, 0.012))

    # crates: one per corner, labels face the room center along X
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        cx, cy = sx * 540.0, sy * 470.0
        mesh_actor(meshes["SM_Style_Crate"], "Crate%d" % (i + 1), (cx, cy, floor_z))
        text_actor("CrateLabel%d" % (i + 1), "SMK-0%d" % (i + 1), (cx - sx * 90.5, cy, floor_z + 70),
                   0.0 if sx < 0 else 180.0, 18, ACCENT)

    # player start at the front end, looking at the stand
    start = actors_sub.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(front_x + 200.0, 0, floor_z + 100.0),
                                              unreal.Rotator(roll=0, pitch=0, yaw=0))
    tag(start, "PlayerStart")

    # sky light: closed room, keep a little fill
    if "Ambient" in by_label:
        by_label["Ambient"].light_component.set_editor_property("intensity", 0.3)

    # exposure: fixed, so the palette stays exact between shots
    if "Look" in by_label:
        pp = by_label["Look"].settings
        pp.set_editor_property("override_auto_exposure_method", True)
        pp.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
        pp.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
        pp.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
        pp.set_editor_property("override_auto_exposure_bias", True)
        pp.set_editor_property("auto_exposure_bias", 0.0)
        pp.set_editor_property("override_bloom_intensity", True)
        pp.set_editor_property("bloom_intensity", 0.35)
        pp.set_editor_property("override_lumen_final_gather_quality", True)
        pp.set_editor_property("lumen_final_gather_quality", 2.0)
        by_label["Look"].set_editor_property("settings", pp)

    # hero camera for screenshots/video; no longer takes over the player view
    if "Camera" in by_label:
        cam = by_label["Camera"]
        src = (-640.0, 0.0, 190.0)
        cam.set_actor_location(unreal.Vector(*src), False, False)
        cam.set_actor_rotation(rot_to(src, (0.0, 0.0, 120.0)), False)
        cam.camera_component.set_editor_property("field_of_view", 70.0)
        cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.DISABLED)

    world = unreal.EditorLevelLibrary.get_editor_world()
    if game_mode is not None:
        world.get_world_settings().set_editor_property("default_game_mode", game_mode)

    unreal.EditorLevelLibrary.save_current_level()


def main():
    mats = build_materials()
    meshes = import_meshes(mats)
    try:
        gm = build_game_mode()
    except Exception as e:  # not critical for the look
        unreal.log_warning("[StyleKit] game mode skipped: %s" % e)
        gm = None
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    build_level(meshes, mats, gm)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("done")


main()
