# part_manager.py
# Part management system for organizing numbered objects
#
# Naming scheme: <prefix><first_digit>.<second_digit>   e.g. Wing1.2
# Objects are grouped by first digit. Anything that doesn't fit is "Misc".
import bpy
import re
from bpy.props import StringProperty, IntProperty
 # CONSTANTS / HELPERS
PART_PATTERN = re.compile(r"^(.*?)(\d+)\.(\d+)$")
MISC_GROUP = -1              # sentinel used by the set-digit operator
MAX_NAME_LENGTH = 63         # Blender's object name limit
MAX_DIGIT = 2**31 - 1        # IntProperty limit
def get_part_match(name):
    """Return (prefix, first_digit, second_digit) as strings, or None.
    Blender's auto duplicate suffixes (Wing1.2.001) are NOT treated as parts,
    otherwise they'd be mis-grouped with a bogus prefix of 'Wing1.'.
    """
    match = PART_PATTERN.match(name)
    if match is None:
        return None
    prefix, first, second = match.groups()
    if prefix.endswith(".") and len(second) == 3:
        return None
    if int(first) > MAX_DIGIT:
        return None
    return prefix, first, second
def is_visible_mesh(obj):
    return obj.type == 'MESH' and not obj.hide_get()
def get_existing_object(name, exclude=None):
    obj = bpy.data.objects.get(name)
    if obj is not None and obj != exclude:
        return obj
    return None
def rename_without_collision(obj, new_name, operator=None):
    """Rename obj to new_name. Returns True on success, False if skipped."""
    if obj.name == new_name:
        return True
    if len(new_name) > MAX_NAME_LENGTH:
        if operator is not None:
            operator.report(
                {'WARNING'},
                f"Cannot rename '{obj.name}': new name exceeds {MAX_NAME_LENGTH} characters")
        return False
    if get_existing_object(new_name, exclude=obj) is not None:
        if operator is not None:
            operator.report(
                {'WARNING'},
                f"Cannot rename '{obj.name}' to '{new_name}': name already exists")
        return False
    obj.name = new_name
    return True
 # OPERATORS
class PartManagerRefreshOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_refresh"
    bl_label = "Refresh Part Manager Groups"
    bl_description = "Redraw the part list"
    def execute(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}
class PartManagerAdjustSecondDigitOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_adjust_second_digit"
    bl_label = "Adjust Second Digit"
    bl_description = "Increase or decrease the second digit of the object name"
    bl_options = {'REGISTER', 'UNDO'}
    target_name: StringProperty()
    delta: IntProperty()
    def execute(self, context):
        obj = bpy.data.objects.get(self.target_name)
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, f"Object '{self.target_name}' not found")
            return {'CANCELLED'}
        parsed = get_part_match(obj.name)
        if parsed is None:
            self.report({'WARNING'}, f"'{obj.name}' has no X.Y digits; assign a group digit first")
            return {'CANCELLED'}
        prefix, first_digit, second_digit = parsed
        new_second = max(0, int(second_digit) + self.delta)
        if new_second > MAX_DIGIT:
            return {'CANCELLED'}
        old_name = obj.name
        if rename_without_collision(obj, f"{prefix}{first_digit}.{new_second}", self):
            self.report({'INFO'}, f"Renamed '{old_name}' to '{obj.name}'")
        return {'FINISHED'}
class PartManagerRenameObjectOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_rename_object"
    bl_label = "Rename Object"
    bl_description = "Rename this object"
    bl_options = {'REGISTER', 'UNDO'}
    old_name: StringProperty()
    new_name: StringProperty(name="New Name")
    def execute(self, context):
        obj = bpy.data.objects.get(self.old_name)
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, f"Object '{self.old_name}' not found")
            return {'CANCELLED'}
        if not self.new_name:
            self.report({'WARNING'}, "Name cannot be empty")
            return {'CANCELLED'}
        old_name = obj.name
        if rename_without_collision(obj, self.new_name, self):
            self.report({'INFO'}, f"Renamed '{old_name}' to '{obj.name}'")
            return {'FINISHED'}
        return {'CANCELLED'}
    def invoke(self, context, event):
        self.new_name = self.old_name
        return context.window_manager.invoke_props_dialog(self)
    def draw(self, context):
        self.layout.prop(self, "new_name")
class PartManagerSetFirstDigitOperator(bpy.types.Operator):
    bl_idname = "object.part_manager_set_first_digit"
    bl_label = "Set First Digit for Group"
    bl_description = "Change the first digit for all objects in this group"
    bl_options = {'REGISTER', 'UNDO'}
    first_digit: IntProperty()   # group to change, or MISC_GROUP (-1) for misc objects
    new_digit: IntProperty(name="New First Digit", default=0, min=0, max=MAX_DIGIT)
    def invoke(self, context, event):
        self.new_digit = max(0, self.first_digit)
        return context.window_manager.invoke_props_dialog(self)
    def draw(self, context):
        self.layout.prop(self, "new_digit")
    def execute(self, context):
        renamed_count = 0
        skipped_count = 0
        for obj in list(context.visible_objects):
            if not is_visible_mesh(obj):
                continue
            parsed = get_part_match(obj.name)
            if self.first_digit == MISC_GROUP:
                if parsed is not None:
                    continue  # already a numbered part, not misc
                # Keep the whole original name as the prefix. Add "_" if the name
                # ends in a digit so it can't merge into the first digit.
                sep = "_" if obj.name[-1:].isdigit() else ""
                new_name = f"{obj.name}{sep}{self.new_digit}.0"
            else:
                if parsed is None or int(parsed[1]) != self.first_digit:
                    continue
                prefix, _, second_digit = parsed
                new_name = f"{prefix}{self.new_digit}.{second_digit}"
            if new_name == obj.name:
                continue
            if rename_without_collision(obj, new_name, self):
                renamed_count += 1
            else:
                skipped_count += 1
        message = f"Renamed {renamed_count} objects"
        if skipped_count:
            message += f"; skipped {skipped_count} due to name conflicts"
        self.report({'INFO'}, message)
        return {'FINISHED'}
 # UI
def draw_part_manager_ui(layout, context):
    """Draw the Part Manager UI section."""
    box = layout.box()
    box.operator("object.part_manager_refresh", text="Refresh Groups", icon='FILE_REFRESH')
    groups = {}            # int first digit -> [(name, int second, key)]
    seen_keys = set()
    duplicate_keys = set()
    misc_objects = []
    for obj in context.visible_objects:
        if not is_visible_mesh(obj):
            continue
        parsed = get_part_match(obj.name)
        if parsed is not None:
            _, first_digit, second_digit = parsed
            first_int, second_int = int(first_digit), int(second_digit)
            # Numeric key so "Cube1.1" and "Cube01.01" count as the same slot.
            # Note: the prefix is ignored, so Wing1.2 and Leg1.2 are flagged as dupes.
            key = (first_int, second_int)
            if key in seen_keys:
                duplicate_keys.add(key)
            seen_keys.add(key)
            groups.setdefault(first_int, []).append((obj.name, second_int, key))
        else:
            misc_objects.append(obj)
    if not groups and not misc_objects:
        box.label(text="No visible meshes found")
        return
    for first_digit in sorted(groups):
        group_box = box.box()
        row = group_box.row(align=True)
        row.label(text=f"Group {first_digit}")
        op = row.operator("object.part_manager_set_first_digit", text="Change Digit...")
        op.first_digit = first_digit
        group_box.label(text="Objects (click + / - to change second digit):")
        for name, second, key in sorted(groups[first_digit], key=lambda x: x[1]):
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
        op = misc_box.operator("object.part_manager_set_first_digit", text="Assign Digit to Misc...")
        op.first_digit = MISC_GROUP
        for obj in misc_objects:
            row = misc_box.row(align=True)
            row.label(text=obj.name)
            # No +/- here: misc objects have no digits to adjust yet.
            op_rename = row.operator("object.part_manager_rename_object", text="", icon='GREASEPENCIL')
            op_rename.old_name = obj.name
 # REGISTRATION
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