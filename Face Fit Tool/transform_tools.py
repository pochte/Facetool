# transform_tools.py
# Mirror, duplication, and transformation tools

import bpy
import bmesh
import re
from bpy.props import EnumProperty, StringProperty, IntProperty

# --- Collection Duplicate ---
def duplicate_collection(col, collection_prefix="", object_prefix="", parent=None):
    new_col = bpy.data.collections.new(f"{collection_prefix}{col.name}")
    if parent is None:
        bpy.context.scene.collection.children.link(new_col)
    else: 
        parent.children.link(new_col)
    for obj in col.objects:
        if obj.type == 'MESH':
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            new_col.objects.link(new_obj)
            new_obj.name = f"{object_prefix}{obj.name}"
        elif obj.type == 'EMPTY' and obj.instance_collection:
            new_empty = obj.copy()
            new_col.objects.link(new_empty)
            new_empty.name = f"{object_prefix}{obj.name}"
            duplicate_collection(obj.instance_collection, collection_prefix, object_prefix, new_col)
    for sub in col.children:
        duplicate_collection(sub, collection_prefix, object_prefix, new_col)

class DuplicateCollectionAsymOperator(bpy.types.Operator):
    bl_idname = "object.duplicate_collection_asym"
    bl_label = "Duplicate Collection"
    bl_description = "Duplicate the active collection with all its objects and sub-collections, adding the specified prefix to all names"
    
    def execute(self, context):
        prefix = context.scene.fft_dup_prefix
        active_col = context.view_layer.active_layer_collection.collection
        if not active_col:
            self.report({'ERROR'}, "Select a collection folder first")
            return {'CANCELLED'}
        duplicate_collection(active_col, collection_prefix=prefix, object_prefix=prefix)
        self.report({'INFO'}, f"Duplicated '{active_col.name}' with prefix '{prefix}'")
        return {'FINISHED'}

# --- Mirror Operators ---
class MirrorToNewObjectOperator(bpy.types.Operator):
    bl_idname = "object.mirror_to_new_object"
    bl_label = "Mirror to New Object"
    bl_description = "Mirror selected mesh to new object, swap vertex groups (_l/_r), choose axes"

    axis: EnumProperty(
        name="Mirror Axis",
        items=[
            ('X', "X Axis", "Mirror along X axis"),
            ('Y', "Y Axis", "Mirror along Y axis"),
            ('Z', "Z Axis", "Mirror along Z axis"),
        ],
        default='X'
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object first")
            return {'CANCELLED'}
        
        mirror_obj = obj.copy()
        mirror_obj.data = obj.data.copy()
        context.collection.objects.link(mirror_obj)
        
        bm = bmesh.new()
        bm.from_mesh(mirror_obj.data)
        for v in bm.verts:
            if self.axis == 'X':
                v.co.x = -v.co.x
            elif self.axis == 'Y':
                v.co.y = -v.co.y
            elif self.axis == 'Z':
                v.co.z = -v.co.z
        
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(mirror_obj.data)
        bm.free()

        mirror_obj.location = obj.location.copy()

        new_name = obj.name
        if re.search("left", new_name, re.IGNORECASE):
            new_name = re.sub("left", "right", new_name, flags=re.IGNORECASE)
        elif re.search("right", new_name, re.IGNORECASE):
            new_name = re.sub("right", "left", new_name, flags=re.IGNORECASE)

        mirror_obj.name = "mirrored_" + new_name

        swap_pattern = re.compile(r'^(.*)(_l|_r)$', re.IGNORECASE)

        for i, vg in enumerate(mirror_obj.vertex_groups):
            vg.name = f"_temp_vg_{i}"

        for orig_vg in obj.vertex_groups:
            vg_name = orig_vg.name
            match = swap_pattern.match(vg_name)
            if match:
                base, side = match.groups()
                if side.lower() == '_l':
                    new_side = '_r' if side.islower() else '_R'
                else:
                    new_side = '_l' if side.islower() else '_L'
                new_name = base + new_side
            else:
                new_name = vg_name
            
            for vg in mirror_obj.vertex_groups:
                if vg.name.startswith("_temp_vg_"):
                    vg.name = new_name
                    break

        self.report({'INFO'}, f"Mirrored object created: {mirror_obj.name}, vertex groups swapped")
        return {'FINISHED'}


class DeleteLeftOperator(bpy.types.Operator):
    bl_idname = "object.delete_left"
    bl_label = "Delete Left Half"
    bl_description = "Delete all vertices on the left side (X < 0) of selected meshes"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                bm.verts.ensure_lookup_table()
                verts_to_remove = [v for v in bm.verts if v.co.x < 0]
                for v in verts_to_remove:
                    bm.verts.remove(v)
                bm.to_mesh(obj.data)
                bm.free()
        self.report({'INFO'}, "Deleted left side of meshes")
        return {'FINISHED'}

class DeleteRightOperator(bpy.types.Operator):
    bl_idname = "object.delete_right"
    bl_label = "Delete Right Half"
    bl_description = "Delete all vertices on the right side (X > 0) of selected meshes"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                bm.verts.ensure_lookup_table()
                verts_to_remove = [v for v in bm.verts if v.co.x > 0]
                for v in verts_to_remove:
                    bm.verts.remove(v)
                bm.to_mesh(obj.data)
                bm.free()
        self.report({'INFO'}, "Deleted right side of meshes")
        return {'FINISHED'}

class MirrorModifierOperator(bpy.types.Operator):
    bl_idname = "object.mirror_modifier"
    bl_label = "Add Mirror Modifier X"
    bl_description = "Add a mirror modifier on the X axis to selected meshes"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                mod = obj.modifiers.new(name="Mirror_X", type='MIRROR')
                mod.use_axis[0] = True
        self.report({'INFO'}, "Mirror modifier added to X axis")
        return {'FINISHED'}

class MirrorModifierUVOperator(bpy.types.Operator):
    bl_idname = "object.mirror_modifier_uv"
    bl_label = "Mirror Modifier UVs"
    bl_description = "Add a mirror modifier with UV mirroring enabled (useful for symmetrical textures)"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                mod = obj.modifiers.new(name="Mirror_UV", type='MIRROR')
                mod.use_axis[0] = True
                mod.use_bisect_axis[0] = False
        self.report({'INFO'}, "Mirror modifier UV added")
        return {'FINISHED'}

# --- Duplicate Object Operator ---
class DuplicateObjectNumberedOperator(bpy.types.Operator):
    bl_idname = "object.duplicate_object_numbered"
    bl_label = "Duplicate Object with Numbering"
    bl_description = "Duplicate the active object with incremental numbering (e.g., 5.0 to 5.1, 5.2, 5.3)"
    
    count: IntProperty(
        name="Count",
        description="Number of duplicates to create",
        default=3,
        min=1,
        max=20
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}
            
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}
        
        base_name = obj.name
        match = re.search(r"(.*?)(\d+)\.(\d+)$", base_name)
        
        if match:
            prefix = match.group(1).strip()
            major = match.group(2)
            minor = int(match.group(3))
        else:
            prefix = base_name.strip()
            major = "0"
            minor = 0
        
        created_count = 0
        for i in range(1, self.count + 1):
            new_minor = minor + i
            new_name = f"{prefix} {major}.{new_minor}" if prefix else f"{major}.{new_minor}"
            
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            
            for coll in obj.users_collection:
                coll.objects.link(new_obj)
            
            new_obj.name = new_name
            new_obj.data.name = new_name
            created_count += 1
        
        self.report({'INFO'}, f"Created {created_count} duplicate(s) of '{base_name}'")
        return {'FINISHED'}

# --- Registration ---
classes = [
    DuplicateCollectionAsymOperator,
    MirrorToNewObjectOperator,
    DeleteLeftOperator,
    DeleteRightOperator,
    MirrorModifierOperator,
    MirrorModifierUVOperator,
    DuplicateObjectNumberedOperator,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)