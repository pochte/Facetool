# mesh_tools.py
# Armature, Material, and Shape Key tools

import bpy
from bpy.props import IntProperty

epsilon = 1e-6

# --- Armature Operators ---
class ToggleArmatureModifierOperator(bpy.types.Operator):
    bl_idname = "object.toggle_armature_modifier"
    bl_label = "Toggle Armature Modifier on ALL Meshes"
    bl_description = "Add or remove the selected armature modifier on all mesh objects in the scene"
    
    def execute(self, context):
        arm_name = context.scene.fft_armature
        arm = bpy.data.objects.get(arm_name)
        if not arm or arm.type != 'ARMATURE':
            self.report({'ERROR'}, f"Armature '{arm_name}' not found")
            return {'CANCELLED'}
        meshes = [o for o in context.scene.objects if o.type == 'MESH']
        for obj in meshes:
            mod = obj.modifiers.get(arm.name)
            if mod and mod.type == 'ARMATURE' and mod.object == arm:
                obj.modifiers.remove(mod)
            else:
                new_mod = obj.modifiers.new(name=arm.name, type='ARMATURE')
                new_mod.object = arm
        for obj in context.scene.objects:
            for mod in obj.modifiers: 
                mod.show_expanded = False
        return {'FINISHED'}

class ResetArmatureModifiersOperator(bpy.types.Operator):
    bl_idname = "object.reset_armature_modifiers"
    bl_label = "Reset All Armature Modifiers"
    bl_description = "Remove all armature modifiers from all mesh objects"
    
    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                for mod in [m for m in obj.modifiers if m.type == 'ARMATURE']:
                    obj.modifiers.remove(mod)
                    count += 1
        self.report({'INFO'}, f"Removed {count} armature modifier(s)")
        return {'FINISHED'}

# --- Material Operators ---
class AssignMaterialOperator(bpy.types.Operator):
    bl_idname = "object.assign_material_to_selected"
    bl_label = "Assign Material to Selected"
    bl_description = "Replace all materials on selected meshes with the chosen material"
    
    def execute(self, context):
        mat_name = context.scene.fft_material
        if mat_name == 'NONE':
            self.report({'ERROR'}, "No material selected")
            return {'CANCELLED'}
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            self.report({'ERROR'}, f"Material '{mat_name}' not found")
            return {'CANCELLED'}
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, "No selected meshes")
            return {'CANCELLED'}
        for obj in meshes:
            obj.data.materials.clear()
            obj.data.materials.append(mat)
        self.report({'INFO'}, f"Assigned '{mat_name}' to {len(meshes)} mesh(es)")
        return {'FINISHED'}

# --- Shape Key Operators ---
class ShapeKeyResetOperator(bpy.types.Operator):
    bl_idname = "object.reset_shapekeys"
    bl_label = "Reset Shape Keys to 0"
    bl_description = "Set all shape key values to 0 and unmute them"
    
    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    if key.name != "Basis":
                        key.value = 0.0
                        key.mute = False
                        count += 1
        self.report({'INFO'}, f"Reset {count} shape keys to 0")
        return {'FINISHED'}

class ShapeKeySetOneOperator(bpy.types.Operator):
    bl_idname = "object.set_shapekeys_one"
    bl_label = "Set Shape Keys to 1"
    bl_description = "Set all shape key values to 1 and unmute them"
    
    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    if key.name != "Basis":
                        key.value = 1.0
                        key.mute = False
                        count += 1
        self.report({'INFO'}, f"Set {count} shape keys to 1")
        return {'FINISHED'}

class ShapeKeyCleanupOperator(bpy.types.Operator):
    bl_idname = "object.cleanup_shapekeys"
    bl_label = "Remove Shape Keys with Zero Values"
    bl_description = "Remove shape keys that have no effect (all vertex deltas are zero), and remove shape key data if only Basis remains"
    
    def execute(self, context):
        count = 0
        removed_shape_key_data = 0
        
        for obj in context.scene.objects:
            if obj.type != 'MESH' or not obj.data.shape_keys: 
                continue
            
            sk = obj.data.shape_keys
            basis = sk.key_blocks.get("Basis")
            if not basis:
                continue
            
            to_remove = []
            for key_block in sk.key_blocks:
                if key_block.name == "Basis":
                    continue
                is_zero = True
                for i, vert in enumerate(key_block.data):
                    if i >= len(basis.data):
                        break
                    delta = (vert.co - basis.data[i].co).length
                    if delta > epsilon:
                        is_zero = False
                        break
                if is_zero:
                    to_remove.append(key_block.name)
            
            for key_name in to_remove:
                idx = sk.key_blocks.find(key_name)
                if idx != -1:
                    obj.active_shape_key_index = idx
                    context.view_layer.objects.active = obj
                    bpy.ops.object.shape_key_remove()
                    count += 1
            
            if obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) == 1:
                basis_name = obj.data.shape_keys.key_blocks[0].name
                if basis_name.lower() in {"basis", "basic"}:
                    obj.shape_key_clear()
                    removed_shape_key_data += 1
        
        if removed_shape_key_data > 0:
            self.report({'INFO'}, f"Removed {count} shape keys and cleared shape key data from {removed_shape_key_data} object(s)")
        else:
            self.report({'INFO'}, f"Removed {count} shape keys")
        return {'FINISHED'}

# --- Registration ---
classes = [
    ToggleArmatureModifierOperator,
    ResetArmatureModifiersOperator,
    AssignMaterialOperator,
    ShapeKeyResetOperator,
    ShapeKeySetOneOperator,
    ShapeKeyCleanupOperator,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)