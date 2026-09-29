# transform_tools.py
# Mirror, duplication, and transformation tools
import bpy
import bmesh
import re
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector
  # CONSTANTS / HELPERS
DUP_PREFIX_PROP = "fft_dup_prefix"
_registered_dup_prefix = False   # True only if this module created the Scene property
SEAM_EPSILON = 1e-5              # keeps seam vertices from being cut by float noise
MAX_DIGIT = 2**31 - 1
PART_PATTERN = re.compile(r"^(.*?)(\d+)\.(\d+)$")
# Whole-word left/right swap that preserves case. Deliberately case-sensitive so
# "Copyright" and "leftover" are untouched but "LeftArm" and "left_to_right" work.
LR_PATTERN = re.compile(r"(?<![A-Za-z])(Left|left|LEFT|Right|right|RIGHT)(?![a-z])")
LR_SWAP = {
    "Left": "Right", "left": "right", "LEFT": "RIGHT",
    "Right": "Left", "right": "left", "RIGHT": "LEFT",
}
SIDE_SUFFIX = re.compile(r"^(.*)([._])([lLrR])$")
# Pointer properties on modifiers/constraints that may reference duplicated objects
OBJECT_REF_ATTRS = ("object", "mirror_object", "offset_object", "target", "auxiliary_target")
def get_part_match(name):
    """Return (prefix, first_digit, second_digit) as strings, or None.
    Blender's auto duplicate suffixes (Wing1.2.001) are not treated as parts."""
    match = PART_PATTERN.match(name)
    if match is None:
        return None
    prefix, first, second = match.groups()
    if prefix.endswith(".") and len(second) == 3:
        return None
    if int(first) > MAX_DIGIT or int(second) > MAX_DIGIT:
        return None
    return prefix, first, second
def swap_left_right(name):
    return LR_PATTERN.sub(lambda m: LR_SWAP[m.group(1)], name)
def swap_side_suffix(name):
    """arm_l <-> arm_r, Arm.L <-> Arm.R (case of the suffix preserved)."""
    match = SIDE_SUFFIX.match(name)
    if match is None:
        return name
    base, sep, side = match.groups()
    swapped = "r" if side.lower() == "l" else "l"
    if side.isupper():
        swapped = swapped.upper()
    return f"{base}{sep}{swapped}"
def require_object_mode(operator, context):
    """bmesh/data copies read stale data while a mesh is in Edit Mode."""
    if context.mode != 'OBJECT':
        operator.report({'ERROR'}, "Switch to Object Mode first")
        return False
    return True
def link_child(parent, child):
    if child.name not in parent.children:
        parent.children.link(child)
  # COLLECTION DUPLICATE
class CollectionDuplicator:
    """Deep-copies a collection tree.
    - Every object type is copied (not just meshes).
    - Shared object data stays shared between the copies.
    - An object or collection reached more than once is only copied once.
    - Instanced collections are copied and the copied instance empties point at
      the copy, not the original. Instance-only copies are NOT linked into the
      scene, so they don't appear as extra visible geometry.
    - Parents, modifier targets, and constraint targets are remapped to the
      copies when the referenced object was duplicated too.
    """
    def __init__(self, collection_prefix="", object_prefix=""):
        self.collection_prefix = collection_prefix
        self.object_prefix = object_prefix
        self.col_map = {}
        self.obj_map = {}
        self.data_map = {}
    def duplicate(self, col):
        if col in self.col_map:
            return self.col_map[col]
        new_col = bpy.data.collections.new(f"{self.collection_prefix}{col.name}")
        self.col_map[col] = new_col   # registered early so cycles can't recurse forever
        for obj in list(col.objects):
            new_col.objects.link(self.copy_object(obj))
        for sub in list(col.children):
            link_child(new_col, self.duplicate(sub))
        return new_col
    def copy_object(self, obj):
        if obj in self.obj_map:
            return self.obj_map[obj]
        new_obj = obj.copy()
        self.obj_map[obj] = new_obj
        if obj.data is not None:
            if obj.data not in self.data_map:
                self.data_map[obj.data] = obj.data.copy()
            new_obj.data = self.data_map[obj.data]
        new_obj.name = f"{self.object_prefix}{obj.name}"
        if obj.instance_type == 'COLLECTION' and obj.instance_collection is not None:
            new_obj.instance_collection = self.duplicate(obj.instance_collection)
        return new_obj
    def remap_references(self):
        for new_obj in self.obj_map.values():
            if new_obj.parent is not None and new_obj.parent in self.obj_map:
                new_obj.parent = self.obj_map[new_obj.parent]
            for item in list(new_obj.modifiers) + list(new_obj.constraints):
                for attr in OBJECT_REF_ATTRS:
                    ref = getattr(item, attr, None)
                    if ref is not None and ref in self.obj_map:
                        try:
                            setattr(item, attr, self.obj_map[ref])
                        except (AttributeError, TypeError, RuntimeError):
                            pass
def duplicate_collection(col, collection_prefix="", object_prefix="", parent=None):
    """Duplicate a collection tree and link the copy under `parent`
    (the scene's root collection by default). Returns the new collection."""
    duplicator = CollectionDuplicator(collection_prefix, object_prefix)
    new_col = duplicator.duplicate(col)
    target = parent if parent is not None else bpy.context.scene.collection
    link_child(target, new_col)
    duplicator.remap_references()
    return new_col
class DuplicateCollectionAsymOperator(bpy.types.Operator):
    bl_idname = "object.duplicate_collection_asym"
    bl_label = "Duplicate Collection"
    bl_description = ("Duplicate the active collection with all its objects and sub-collections, "
                      "adding the specified prefix to all names")
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not require_object_mode(self, context):
            return {'CANCELLED'}
        prefix = getattr(context.scene, DUP_PREFIX_PROP, "")
        if not prefix:
            self.report({'ERROR'}, "Set a prefix first (an empty prefix would just create .001 names)")
            return {'CANCELLED'}
        active_col = context.view_layer.active_layer_collection.collection
        if active_col is None or active_col == context.scene.collection:
            self.report({'ERROR'}, "Select a collection (not the Scene Collection) first")
            return {'CANCELLED'}
        duplicate_collection(active_col, collection_prefix=prefix, object_prefix=prefix)
        self.report({'INFO'}, f"Duplicated '{active_col.name}' with prefix '{prefix}'")
        return {'FINISHED'}
  # MIRROR OPERATORS
class MirrorToNewObjectOperator(bpy.types.Operator):
    bl_idname = "object.mirror_to_new_object"
    bl_label = "Mirror to New Object"
    bl_description = ("Mirror selected meshes to new objects, swapping left/right in names and "
                      "_l/_r vertex groups")
    bl_options = {'REGISTER', 'UNDO'}
    axis: EnumProperty(
        name="Mirror Axis",
        items=[
            ('X', "X Axis", "Mirror along X axis"),
            ('Y', "Y Axis", "Mirror along Y axis"),
            ('Z', "Z Axis", "Mirror along Z axis"),
        ],
        default='X'
    )
    mirror_location: BoolProperty(
        name="Mirror Position",
        description=("Mirror the object's transform across the world origin. "
                     "Turn off to keep the copy at the original's position"),
        default=True
    )
    def execute(self, context):
        if not require_object_mode(self, context):
            return {'CANCELLED'}
        sources = [o for o in context.selected_objects if o.type == 'MESH']
        active = context.active_object
        if not sources and active is not None and active.type == 'MESH':
            sources = [active]
        if not sources:
            self.report({'ERROR'}, "Select a mesh object first")
            return {'CANCELLED'}
        axis_index = "XYZ".index(self.axis)
        axis_vec = Vector((1.0 if i == axis_index else 0.0 for i in range(3)))
        flip = Matrix.Scale(-1.0, 4, axis_vec)
        created = [self.mirror_one(context, obj, axis_index, flip) for obj in sources]
        self.report({'INFO'}, f"Created {len(created)} mirrored object(s), vertex groups swapped")
        return {'FINISHED'}
    def mirror_one(self, context, obj, axis_index, flip):
        mirror_obj = obj.copy()
        mirror_obj.data = obj.data.copy()
        context.collection.objects.link(mirror_obj)
        # Flip the mesh (and every shape key) in local space, then fix winding.
        mesh = mirror_obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh, use_shape_key=True)
        shape_layers = list(bm.verts.layers.shape.values())
        for v in bm.verts:
            v.co[axis_index] = -v.co[axis_index]
            for layer in shape_layers:
                co = v[layer]
                co[axis_index] = -co[axis_index]
                v[layer] = co
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        # World-space mirror of the object transform: S @ W @ S, paired with the
        # local flip above, gives world verts = S @ (original world verts).
        if self.mirror_location:
            mirror_obj.matrix_world = flip @ obj.matrix_world @ flip
        mirror_obj.name = "mirrored_" + swap_side_suffix(swap_left_right(obj.name))
        # Vertex groups keep their order from the copy. Go through temp names so
        # swapped names (arm_l <-> arm_r) never collide mid-rename.
        for i, vg in enumerate(mirror_obj.vertex_groups):
            vg.name = f"_temp_vg_{i}"
        for i, vg in enumerate(mirror_obj.vertex_groups):
            vg.name = swap_side_suffix(obj.vertex_groups[i].name)
        return mirror_obj
def delete_mesh_half(operator, context, side):
    """Delete verts on one side of X (local space) for all selected meshes."""
    if not require_object_mode(operator, context):
        return {'CANCELLED'}
    processed = set()
    removed_total = 0
    for obj in context.selected_objects:
        if obj.type != 'MESH' or obj.data in processed:
            continue
        processed.add(obj.data)   # shared mesh data is only cut once
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh, use_shape_key=True)
        if side == 'LEFT':
            doomed = [v for v in bm.verts if v.co.x < -SEAM_EPSILON]
        else:
            doomed = [v for v in bm.verts if v.co.x > SEAM_EPSILON]
        if doomed:
            # Remember geometry around the cut so leftover wire edges can be cleaned up.
            touched_edges = set()
            touched_verts = set()
            for v in doomed:
                for f in v.link_faces:
                    touched_edges.update(f.edges)
                    touched_verts.update(f.verts)
            bmesh.ops.delete(bm, geom=doomed, context='VERTS')
            for e in touched_edges:
                if e.is_valid and not e.link_faces:
                    bm.edges.remove(e)
            for v in touched_verts:
                if v.is_valid and not v.link_edges:
                    bm.verts.remove(v)
            bm.to_mesh(mesh)
            mesh.update()
            removed_total += len(doomed)
        bm.free()
    if not processed:
        operator.report({'WARNING'}, "No mesh objects selected")
        return {'CANCELLED'}
    label = "left" if side == 'LEFT' else "right"
    operator.report({'INFO'}, f"Deleted {removed_total} vertices on the {label} side")
    return {'FINISHED'}
class DeleteLeftOperator(bpy.types.Operator):
    bl_idname = "object.delete_left"
    bl_label = "Delete Left Half"
    bl_description = "Delete all vertices on the left side (X < 0) of selected meshes"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        return delete_mesh_half(self, context, 'LEFT')
class DeleteRightOperator(bpy.types.Operator):
    bl_idname = "object.delete_right"
    bl_label = "Delete Right Half"
    bl_description = "Delete all vertices on the right side (X > 0) of selected meshes"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        return delete_mesh_half(self, context, 'RIGHT')
class MirrorModifierOperator(bpy.types.Operator):
    bl_idname = "object.mirror_modifier"
    bl_label = "Add Mirror Modifier X"
    bl_description = "Add a mirror modifier on the X axis to selected meshes"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                mod = obj.modifiers.new(name="Mirror_X", type='MIRROR')
                mod.use_axis[0] = True
                count += 1
        if count == 0:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        self.report({'INFO'}, "Mirror modifier added to X axis")
        return {'FINISHED'}
class MirrorModifierUVOperator(bpy.types.Operator):
    bl_idname = "object.mirror_modifier_uv"
    bl_label = "Mirror Modifier UVs"
    bl_description = ("Add an X mirror modifier that also mirrors UVs (U flipped around 0.5), "
                      "so the mirrored half gets its own side of UV space")
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                mod = obj.modifiers.new(name="Mirror_UV", type='MIRROR')
                mod.use_axis[0] = True
                mod.use_mirror_u = True
                count += 1
        if count == 0:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        self.report({'INFO'}, "Mirror modifier with UV mirroring added")
        return {'FINISHED'}
  # DUPLICATE OBJECT (NUMBERED)
class DuplicateObjectNumberedOperator(bpy.types.Operator):
    bl_idname = "object.duplicate_object_numbered"
    bl_label = "Duplicate Object with Numbering"
    bl_description = "Duplicate the active object with incremental numbering (e.g., Wing5.0 to Wing5.1, Wing5.2, Wing5.3)"
    bl_options = {'REGISTER', 'UNDO'}
    count: IntProperty(
        name="Count",
        description="Number of duplicates to create",
        default=3,
        min=1,
        max=20
    )
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    def draw(self, context):
        self.layout.prop(self, "count")
    def execute(self, context):
        if not require_object_mode(self, context):
            return {'CANCELLED'}
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}
        base_name = obj.name
        parsed = get_part_match(base_name)
        if parsed:
            prefix, major, minor_str = parsed
            minor = int(minor_str)
        else:
            # Same convention as part_manager: <name><first>.<second>, with "_"
            # so a trailing digit in the name can't merge into the first digit.
            prefix = base_name + ("_" if base_name[-1:].isdigit() else "")
            major = "0"
            minor = 0
        created_count = 0
        next_minor = minor
        for _ in range(self.count):
            # Skip numbers that are already taken instead of getting ".001" names.
            while True:
                next_minor += 1
                new_name = f"{prefix}{major}.{next_minor}"
                if new_name not in bpy.data.objects:
                    break
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            for coll in obj.users_collection:
                coll.objects.link(new_obj)
            new_obj.name = new_name
            new_obj.data.name = new_name
            created_count += 1
        self.report({'INFO'}, f"Created {created_count} duplicate(s) of '{base_name}'")
        return {'FINISHED'}
  # REGISTRATION
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
    global _registered_dup_prefix
    for cls in classes:
        bpy.utils.register_class(cls)
    # The duplicate operator reads this; only define it if nobody else has.
    if not hasattr(bpy.types.Scene, DUP_PREFIX_PROP):
        setattr(bpy.types.Scene, DUP_PREFIX_PROP,
                StringProperty(name="Duplicate Prefix", default="copy_"))
        _registered_dup_prefix = True
def unregister():
    global _registered_dup_prefix
    if _registered_dup_prefix and hasattr(bpy.types.Scene, DUP_PREFIX_PROP):
        delattr(bpy.types.Scene, DUP_PREFIX_PROP)
    _registered_dup_prefix = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)