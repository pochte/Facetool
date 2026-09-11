bl_info = {
    "name": "Face Fit Tools",
    "author": "Ulli",
    "version": (3, 3),
    "blender": (4, 0, 0),
    "description": "Face presets, armature toggling, material assign, collection duplication, shape key toggle/cleanup, and part management tools",
    "category": "Object",
}

import bpy
import re
from bpy.props import EnumProperty, BoolProperty, StringProperty, IntProperty

# Import modules
from . import mesh_tools
from . import transform_tools
from . import part_manager

# --- Face Fit UI Data ---
RACE_ITEMS = [
    ('highlander', "Highlander", ""),
    ('midlander', "Midlander", ""),
    ('roegadyn', "Roegadyn", ""),
    ('elezen', "Elezen", ""),
    ('miqote', "Miqote", ""),
    ('aura', "Aura", ""),
    ('viera', "Viera", ""),
    ('hrothgar', "Hrothgar", ""),
]

GENDER_ITEMS = [
    ('male', "Male", ""),
    ('female', "Female", ""),
    ('child', "Child", ""),
]

def get_face_items(self, context):
    if context is None or context.scene is None:
        return [('1', "Face 1", "")]
    race = (context.scene.fft_race or "highlander").lower()
    gender = (context.scene.fft_gender or "female").lower()
    face_ids = set()
    dnt_collection = bpy.data.collections.get("DO NOT TOUCH")
    if not dnt_collection:
        return [('1', "Face 1", "")]
    valid_id_pattern = re.compile(r'^[\w\-]+$')

    def scan_collection(collection):
        for obj in collection.objects:
            if obj.type == 'EMPTY':
                parts = obj.name.lower().split()
                if len(parts) == 3:
                    obj_race, obj_gender, obj_face = parts
                    if obj_race == race and obj_gender == gender:
                        if valid_id_pattern.match(obj_face):
                            face_ids.add(obj_face)
        for child in collection.children:
            scan_collection(child)

    scan_collection(dnt_collection)
    if not face_ids:
        face_ids = {'1', '2', '3', '4'}
    def sort_key(x):
        try: 
            return int(x)
        except: 
            return float('inf')
    return [(f, "Face " + f, "") for f in sorted(face_ids, key=sort_key)]

def get_armature_items(self, context):
    if context is None or context.scene is None:
        return [('NONE', 'No Armatures Found', '')]
    items = []
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE' and (obj.parent is None or obj.parent.type != 'ARMATURE'):
            items.append((obj.name, obj.name, ""))
    if not items: 
        items.append(('NONE', 'No Top-Level Armatures Found', ''))
    return items

def get_material_items(self, context):
    mats = bpy.data.materials
    if mats:
        return [(mat.name, mat.name, "") for mat in mats]
    return [('NONE', 'No Materials Found', '')]

def armature_selection_update(self, context):
    selected_name = context.scene.fft_armature
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE':
            hide = (selected_name != obj.name) if selected_name != 'NONE' else True
            obj.hide_viewport = hide
            obj.hide_set(hide)

# --- Face Fit Operators ---
class FaceFitApplyOperator(bpy.types.Operator):
    bl_idname = "object.face_fit_apply"
    bl_label = "Apply Face Fit"
    bl_description = "Apply the selected race, gender, and face preset to the Position Controller"
    
    def execute(self, context):
        race = context.scene.fft_race.capitalize()
        gender = context.scene.fft_gender.capitalize()
        face = context.scene.fft_face
        target_name = f"{race} {gender} {face}"
        dnt_collection = bpy.data.collections.get("DO NOT TOUCH")
        if not dnt_collection:
            self.report({'ERROR'}, "Collection 'DO NOT TOUCH' not found!")
            return {'CANCELLED'}
        
        def find_empty(col, target):
            for obj in col.objects:
                if obj.type == 'EMPTY' and target.lower() in obj.name.lower(): 
                    return obj
            for child in col.children:
                r = find_empty(child, target)
                if r: 
                    return r
            return None
        
        empty_obj = find_empty(dnt_collection, target_name)
        target_obj = bpy.data.objects.get("Position Controller")
        if not empty_obj:
            self.report({'ERROR'}, f"No matching empty found for '{target_name}'")
            return {'CANCELLED'}
        if not target_obj:
            self.report({'ERROR'}, "Object named 'Position Controller' not found")
            return {'CANCELLED'}
        target_obj.location = empty_obj.location.copy()
        target_obj.rotation_euler = empty_obj.rotation_euler.copy()
        target_obj.scale = empty_obj.scale.copy()
        self.report({'INFO'}, f"Applied transform from '{empty_obj.name}'")
        return {'FINISHED'}

class FaceFitResetOperator(bpy.types.Operator):
    bl_idname = "object.face_fit_reset"
    bl_label = "Reset Controller to Origin"
    bl_description = "Move the Position Controller back to the Origin empty's location"

    def execute(self, context):
        obj = bpy.data.objects.get("Position Controller")
        if not obj:
            self.report({'ERROR'}, "Object named 'Position Controller' not found")
            return {'CANCELLED'}
        origin_empty = bpy.data.objects.get("Origin")
        if not origin_empty:
            self.report({'ERROR'}, "Empty named 'Origin' not found")
            return {'CANCELLED'}
        obj.location = origin_empty.location
        obj.rotation_euler = origin_empty.rotation_euler
        obj.scale = origin_empty.scale
        self.report({'INFO'}, "Position Controller moved to Origin")
        return {'FINISHED'}

# --- UI Panel ---
class MasterToolPanel(bpy.types.Panel):
    bl_label = "Master Face Fit + Tools"
    bl_idname = "VIEW3D_PT_master_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Master Tools'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        row = box.row()
        row.prop(scene, "fft_show_facefit", icon="TRIA_DOWN" if scene.fft_show_facefit else "TRIA_RIGHT", text="Face Fit", emboss=False)
        if scene.fft_show_facefit:
            box.prop(scene, "fft_race")
            box.prop(scene, "fft_gender")
            box.prop(scene, "fft_face")
            row = box.row()
            row.operator("object.face_fit_apply")
            row.operator("object.face_fit_reset")

        box = layout.box()
        row = box.row()
        row.prop(scene, "fft_show_armature_materials", icon="TRIA_DOWN" if scene.fft_show_armature_materials else "TRIA_RIGHT", text="Armature/Material", emboss=False)
        if scene.fft_show_armature_materials:
            box.prop(scene, "fft_armature")
            row = box.row()
            row.operator("object.toggle_armature_modifier")
            row.operator("object.reset_armature_modifiers")
            box.prop(scene, "fft_material")
            box.operator("object.assign_material_to_selected")

        box = layout.box()
        row = box.row()
        row.prop(scene, "fft_show_collection", icon="TRIA_DOWN" if scene.fft_show_collection else "TRIA_RIGHT", text="Collection Duplicate", emboss=False)
        if scene.fft_show_collection:
            box.prop(scene, "fft_dup_prefix")
            box.operator("object.duplicate_collection_asym")

        box = layout.box()
        row = box.row()
        row.prop(scene, "fft_show_shapekeys", icon="TRIA_DOWN" if scene.fft_show_shapekeys else "TRIA_RIGHT", text="Shape Keys", emboss=False)
        if scene.fft_show_shapekeys:
            row = box.row()
            row.operator("object.reset_shapekeys", text="Reset to 0")
            row.operator("object.set_shapekeys_one", text="Set to 1")
            box.operator("object.cleanup_shapekeys")
            
            box.separator()
            col = box.column()
            row = col.row(align=True)
            row.prop(scene, "fft_duplicate_count", text="Count")
            op = row.operator("object.duplicate_object_numbered", text="Duplicate +Numbers", icon='DUPLICATE')
            op.count = scene.fft_duplicate_count

        box = layout.box()
        row = box.row()
        row.prop(scene, "fft_show_asym", icon="TRIA_DOWN" if scene.fft_show_asym else "TRIA_RIGHT", text="Asymmetry/Mirror", emboss=False)
        if scene.fft_show_asym:
            row = box.row()
            row.operator("object.delete_left")
            row.operator("object.delete_right")
            row = box.row()
            row.operator("object.mirror_modifier")
            row.operator("object.mirror_modifier_uv")
            row = box.row()
            row.operator("object.mirror_to_new_object", text="Mirror to New Object")

        row = layout.row()
        row.prop(scene, "fft_show_part_manager", icon='TRIA_DOWN' if scene.fft_show_part_manager else 'TRIA_RIGHT', text="Part Manager", emboss=False)
        if scene.fft_show_part_manager:
            part_manager.draw_part_manager_ui(layout, context)


def register_props():
    scene = bpy.types.Scene
    scene.fft_show_facefit = BoolProperty(default=True)
    scene.fft_race = EnumProperty(items=RACE_ITEMS, default='highlander')
    scene.fft_gender = EnumProperty(items=GENDER_ITEMS, default='female')
    scene.fft_face = EnumProperty(items=get_face_items)
    scene.fft_show_armature_materials = BoolProperty(default=True)
    scene.fft_armature = EnumProperty(items=get_armature_items, update=armature_selection_update)
    scene.fft_material = EnumProperty(items=get_material_items)
    scene.fft_show_collection = BoolProperty(default=True)
    scene.fft_dup_prefix = StringProperty(default="")
    scene.fft_show_shapekeys = BoolProperty(default=True)
    scene.fft_show_asym = BoolProperty(default=True)
    scene.fft_show_part_manager = BoolProperty(default=True)
    scene.pm_misc_first_digit = IntProperty(name="Misc First Digit", default=0)
    scene.fft_duplicate_count = IntProperty(name="Duplicate Count", default=3, min=1, max=20)

classes = [
    FaceFitApplyOperator,
    FaceFitResetOperator,
    MasterToolPanel,
]

def register():
    # Register modules first
    mesh_tools.register()
    transform_tools.register()
    part_manager.register()
    
    # Register main classes
    for cls in classes: 
        bpy.utils.register_class(cls)
    
    # Register properties
    register_props()

def unregister():
    # Unregister properties
    scene = bpy.types.Scene
    props = [
        "fft_show_facefit", "fft_race", "fft_gender", "fft_face", 
        "fft_show_armature_materials", "fft_armature", "fft_material", 
        "fft_show_collection", "fft_dup_prefix", "fft_show_shapekeys",
        "fft_show_asym", "fft_show_part_manager", "pm_misc_first_digit", 
        "fft_duplicate_count"
    ]
    for p in props: 
        if hasattr(scene, p):
            delattr(scene, p)
    
    scene_props = [attr for attr in dir(scene) if attr.startswith('pm_first_digit_')]
    for prop in scene_props:
        try:
            delattr(scene, prop)
        except:
            pass
    
    # Unregister main classes
    for cls in reversed(classes): 
        bpy.utils.unregister_class(cls)
    
    # Unregister modules
    part_manager.unregister()
    transform_tools.unregister()
    mesh_tools.unregister()

if __name__ == "__main__":
    register()