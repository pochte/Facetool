# part_manager.py
# Part management system for organizing numbered objects

import bpy
import re
from bpy.props import StringProperty, IntProperty

# --- Part Manager Operators ---
class PartManagerRefreshOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_refresh"
    bl_label = "Refresh Part Manager Groups"
    bl_description = "Scan visible meshes and group by number"

    def execute(self, context):
        pattern = re.compile(r"^(?:.*\s)?(\d+)\.(\d+)$")
        first_digits = set()

        for obj in context.visible_objects:
            if obj.type != 'MESH' or obj.hide_get():
                continue
            match = pattern.match(obj.name)
            if match:
                first_digits.add(match.group(1))

        created_count = 0
        for first_digit in first_digits:
            prop_name = f"pm_first_digit_{first_digit}"
            if not hasattr(bpy.types.Scene, prop_name):
                setattr(bpy.types.Scene, prop_name, IntProperty(name=f"Group {first_digit}", default=int(first_digit)))
                created_count += 1

        self.report({'INFO'}, f"Refreshed {len(first_digits)} groups, created {created_count} new properties")
        return {'FINISHED'}


class PartManagerAdjustSecondDigitOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_adjust_second_digit"
    bl_label = "Adjust Second Digit"
    bl_description = "Increase or decrease the second digit of the object name"
    target_name: StringProperty()
    delta: IntProperty()

    def execute(self, context):
        pattern = re.compile(r"^(.*?)(\d+)\.(\d+)$")
        for obj in context.visible_objects:
            if obj.type != 'MESH' or obj.hide_get():
                continue
            if obj.name == self.target_name:
                match = pattern.match(obj.name)
                if match:
                    prefix, first_digit, second_digit = match.groups()
                    new_second = int(second_digit) + self.delta
                    new_second = max(0, new_second)
                    obj.name = f"{prefix}{first_digit}.{new_second}"
                else:
                    if '.' in obj.name:
                        base, second = obj.name.rsplit('.', 1)
                        try:
                            second_val = int(second)
                        except ValueError:
                            second_val = 0
                        new_second = max(0, second_val + self.delta)
                        obj.name = f"{base}.{new_second}"
                    else:
                        if self.delta > 0:
                            obj.name = f"{obj.name}.{self.delta}"
                        else:
                            obj.name = f"{obj.name}.0"
                break
        return {'FINISHED'}


class PartManagerRenameObjectOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_rename_object"
    bl_label = "Rename Object"
    bl_description = "Rename this object"
    
    old_name: StringProperty()
    new_name: StringProperty(name="New Name")
    
    def execute(self, context):
        for obj in context.visible_objects:
            if obj.type == 'MESH' and obj.name == self.old_name:
                obj.name = self.new_name
                self.report({'INFO'}, f"Renamed to '{obj.name}'")
                break
        return {'FINISHED'}
    
    def invoke(self, context, event):
        self.new_name = self.old_name
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_name")


class PartManagerSetFirstDigitOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_set_first_digit"
    bl_label = "Set First Digit for Group"
    bl_description = "Change the first digit for all objects in this group"
    first_digit: IntProperty()
    new_digit: IntProperty()

    def execute(self, context):
        pattern = re.compile(r"^(.*?)(\d+)\.(\d+)$")
        renamed_count = 0
        for obj in context.visible_objects:
            if obj.type != 'MESH' or obj.hide_get():
                continue
            match = pattern.match(obj.name)
            if match and int(match.group(2)) == self.first_digit:
                obj.name = f"{match.group(1)}{self.new_digit}.{match.group(3)}"
                renamed_count += 1
            elif self.first_digit == -1:
                if '.' in obj.name:
                    base, second = obj.name.rsplit('.', 1)
                    try:
                        int(second)
                        obj.name = f"{self.new_digit}.{second}"
                    except ValueError:
                        obj.name = f"{obj.name}.{self.new_digit}.0"
                else:
                    obj.name = f"{self.new_digit}.0"
                renamed_count += 1
        self.report({'INFO'}, f"Renamed {renamed_count} objects")
        return {'FINISHED'}


# --- UI Drawing Function ---
def draw_part_manager_ui(layout, context):
    """Draws the Part Manager UI section"""
    box = layout.box()
    box.operator("object.part_manager_refresh", text="Refresh Groups", icon='FILE_REFRESH')

    pattern = re.compile(r"^(.*?)(\d+)\.(\d+)$")
    groups = {}
    seen_keys = {}
    duplicate_keys = set()
    misc_objects = []

    for obj in context.visible_objects:
        if obj.type != 'MESH' or obj.hide_get():
            continue
        match = pattern.match(obj.name)
        if match:
            prefix, first_digit, second_digit = match.groups()
            key = f"{first_digit}.{second_digit}"
            
            if key in seen_keys:
                duplicate_keys.add(key)
            
            seen_keys[key] = obj
            groups.setdefault(first_digit, []).append((obj.name, int(second_digit), key))
        else:
            misc_objects.append(obj)

    if not groups and not misc_objects:
        box.label(text="No visible meshes found")
    else:
        scene = context.scene
        
        for first_digit in sorted(groups, key=lambda x: int(x)):
            group_box = box.box()
            names_with_digits = sorted(groups[first_digit], key=lambda x: x[1])

            row = group_box.row(align=True)
            row.label(text=f"Group {first_digit}")
            prop_name = f"pm_first_digit_{first_digit}"
            if hasattr(scene, prop_name):
                row.prop(scene, prop_name, text="")
                op = row.operator("object.part_manager_set_first_digit", text="Apply")
                op.first_digit = int(first_digit)
                op.new_digit = getattr(scene, prop_name)
            else:
                row.label(text=f"{first_digit} (click Refresh Groups)")

            group_box.label(text="Objects (click + / - to change second digit):")
            for name, second, key in names_with_digits:
                row = group_box.row(align=True)
                if key in duplicate_keys:
                    row.alert = True
                    row.label(text=name, icon='ERROR')
                else:
                    row.label(text=name)
                
                op_rename = row.operator("object.part_manager_rename_object", text="", icon='GREASEPENCIL')
                op_rename.old_name = name
                
                op_minus = row.operator("object.part_manager_adjust_second_digit", text="", icon='REMOVE')
                op_minus.target_name = name
                op_minus.delta = -1
                op_plus = row.operator("object.part_manager_adjust_second_digit", text="", icon='ADD')
                op_plus.target_name = name
                op_plus.delta = 1

        if misc_objects:
            misc_box = box.box()
            misc_box.label(text="Misc (no X.Y digits)")
            if not hasattr(scene, "pm_misc_first_digit"):
                scene.pm_misc_first_digit = 0
            misc_box.prop(scene, "pm_misc_first_digit", text="First Digit for Misc")
            op = misc_box.operator("object.part_manager_set_first_digit", text="Apply to Misc")
            op.first_digit = -1
            op.new_digit = scene.pm_misc_first_digit
            for obj in misc_objects:
                row = misc_box.row(align=True)
                row.label(text=obj.name)
                op_rename = row.operator("object.part_manager_rename_object", text="", icon='GREASEPENCIL')
                op_rename.old_name = obj.name
                op_minus = row.operator("object.part_manager_adjust_second_digit", text="", icon='REMOVE')
                op_minus.target_name = obj.name
                op_minus.delta = -1
                op_plus = row.operator("object.part_manager_adjust_second_digit", text="", icon='ADD')
                op_plus.target_name = obj.name
                op_plus.delta = 1


# --- Registration ---
classes = [
    PartManagerRefreshOperator,
    PartManagerRenameObjectOperator,
    PartManagerSetFirstDigitOperator,
    PartManagerAdjustSecondDigitOperator,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)