"""Independent archive provenance and image checks for the rendering fixture."""
import json
import math
import pathlib
import struct
from PIL import Image
from verify_web_startup import unpack


def verify_records(records, archive):
    files = unpack(archive)
    initial = records["initial"]
    expected = {"BlueCube": ([-1, 0, -7], [1.2, .8, 1]), "BlueRepeated": ([.25, -1.5, -8], [.5, .5, .5]), "OrangeTetra": ([1.25, 0, -6], [1, 1, 1])}
    assert len(initial["draws"]) == 3
    for draw in initial["draws"]:
        position, scale = expected[draw["object"]]
        for actual, value in zip(draw["model"][12:15], position):
            # Native scene transform composition uses SSE reciprocal estimates;
            # allow 0.005 world units, less than one projected pixel here.
            assert math.isclose(actual, value, abs_tol=.005), draw
        for index, value in zip((0, 5, 10), scale):
            assert math.isclose(draw["model"][index], value, abs_tol=1e-5), draw
            assert math.isclose(draw["normals"][index], 1/value, abs_tol=1e-5), draw
        uid = draw["geometry"].split(":", 1)[1].split("+", 1)[0]
        path = next(path for path in files if path.endswith(uid + ".gltf"))
        model = json.loads(files[path])
        primitive = model["meshes"][0]["primitives"][0]
        binary = files[str(pathlib.PurePosixPath(path).parent / model["buffers"][0]["uri"])]
        payload = bytearray()
        for key, width in (("POSITION", 12), ("NORMAL", 12), ("indices", 2)):
            accessor = model["accessors"][primitive[key] if key == "indices" else primitive["attributes"][key]]
            view = model["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            stride = view.get("byteStride", width)
            for index in range(accessor["count"]):
                payload.extend(binary[offset+index*stride:offset+index*stride+width])
        hash_value = 14695981039346656037
        for byte in payload:
            hash_value = ((hash_value ^ byte) * 1099511628211) & ((1 << 64)-1)
        assert draw["geometryHash"] == str(hash_value), draw
    cubes = [draw for draw in initial["draws"] if draw["object"].startswith("Blue")]
    assert cubes[0]["geometry"] == cubes[1]["geometry"] and cubes[0]["geometryHash"] == cubes[1]["geometryHash"]
    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    for record in records.values():
        for draw in record["draws"]:
            a, b, c = (draw["model"][offset:offset+3] for offset in (0, 4, 8))
            columns = (cross(b, c), cross(c, a), cross(a, b))
            determinant = sum(left*right for left, right in zip(a, columns[0]))
            assert determinant > 0
            for column, values in enumerate(columns):
                for row, value in enumerate(values):
                    assert math.isclose(draw["normals"][column*4+row], value/determinant, abs_tol=.001, rel_tol=.001), draw


def verify_image(path, empty=False):
    image = Image.open(path).convert("RGB")
    # DWM rounded corners can expose a few desktop pixels even in client
    # captures. Inspect the interior; the fixture geometry is well inside it.
    image = image.crop((4, 4, image.width - 4, image.height - 4))
    blue = orange = 0
    for r, g, b in image.getdata():
        blue += b > r * 1.5 and b > g * 1.15 and b > 60
        orange += r > b * 1.5 and r > g * 1.15 and r > 60
    if empty:
        assert blue == orange == 0, (blue, orange)
    else:
        # Broad color-area tolerances catch blank/missing geometry, without
        # requiring pixel-identical rasterization or timing across backends.
        assert blue > 500 and orange > 100, (blue, orange)
        assert blue + orange < image.width * image.height * .65, (blue, orange)
    return dict(bluePixels=blue, orangePixels=orange, width=image.width, height=image.height)


def verify_projection(path, record, archive):
    """Sample an independent CPU rasterization for framing, depth and lighting."""
    files = unpack(archive)
    settings = json.loads(files["config/rendering.json"])["lighting"]
    image = Image.open(path).convert("RGB")
    width, height = image.size
    projection = list(record["viewProjection"])
    projection[0] = projection[5] / (width/height)
    def multiply(matrix, vector):
        return [sum(matrix[column*4+row]*vector[column] for column in range(4)) for row in range(4)]
    triangles = []
    for draw in record["draws"]:
        uid = draw["geometry"].split(":", 1)[1].split("+", 1)[0]
        path_in_pack = next(path for path in files if path.endswith(uid + ".gltf"))
        model = json.loads(files[path_in_pack])
        primitive = model["meshes"][0]["primitives"][0]
        binary = files[str(pathlib.PurePosixPath(path_in_pack).parent / model["buffers"][0]["uri"])]
        def read(index, format):
            accessor = model["accessors"][index]
            view = model["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            size = struct.calcsize(format)
            return [struct.unpack_from(format, binary, offset+i*view.get("byteStride", size)) for i in range(accessor["count"])]
        positions = read(primitive["attributes"]["POSITION"], "<3f")
        normals = read(primitive["attributes"]["NORMAL"], "<3f")
        indices = [value[0] for value in read(primitive["indices"], "<H")]
        vertices = []
        for position, normal in zip(positions, normals):
            clip = multiply(projection, multiply(draw["model"], [*position, 1]))
            assert clip[3] > 0
            vertices.append(((clip[0]/clip[3]+1)*width/2, (1-clip[1]/clip[3])*height/2, clip[2]/clip[3], 1/clip[3], multiply(draw["normals"], [*normal, 0])[:3]))
        for offset in range(0, len(indices), 3):
            triangles.append(([vertices[index] for index in indices[offset:offset+3]], draw["color"]))
    checked, matched, overlap = 0, 0, 0
    for y in range(8, height-8, 12):
        for x in range(8, width-8, 12):
            hits = []
            for vertices, color in triangles:
                a, b, c = vertices
                denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(denominator) < 1e-8:
                    continue
                u = ((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/denominator
                v = ((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/denominator
                barycentric = (u, v, 1-u-v)
                if min(barycentric) < 0:
                    continue
                depth = sum(weight*vertex[2] for weight, vertex in zip(barycentric, vertices))
                normal = [sum(weight*vertex[3]*vertex[4][axis] for weight, vertex in zip(barycentric, vertices)) for axis in range(3)]
                length = math.sqrt(sum(value*value for value in normal))
                diffuse = max(0, sum(left*right/length for left, right in zip(normal, settings["direction"])))
                rgb = []
                for base, ambient, light in zip(color, settings["ambient"], settings["directional"]):
                    linear = min(1, max(0, base*(ambient+light*diffuse)))
                    rgb.append(round(255*(12.92*linear if linear <= .0031308 else 1.055*linear**(1/2.4)-.055)))
                hits.append((depth, rgb, color, min(barycentric)))
            if not hits:
                continue
            nearest = min(hits, key=lambda hit: hit[0])
            if nearest[3] < .015:
                continue
            expected = nearest[1]
            actual = image.getpixel((x, y))
            checked += 1
            matched += max(abs(left-right) for left, right in zip(actual, expected)) <= 25
            overlap += len({tuple(hit[2]) for hit in hits}) > 1
    assert checked > 50 and matched/checked > .94, (checked, matched, overlap)
    return dict(samples=checked, matched=matched, overlapSamples=overlap, channelTolerance=25, requiredMatch=.94)
