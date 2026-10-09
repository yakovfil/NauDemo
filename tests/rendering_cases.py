"""Independent archive mutations for checked rendering failure acceptance."""
import json
from verify_web_startup import pack, unpack, read_scene, write_scene

CONTENT_FAILURES = ("missing-material", "corrupt-material", "missing-geometry", "corrupt-geometry", "unsupported-topology", "unsupported-skinning", "invalid-indices", "invalid-camera", "no-camera", "singular-transform", "reflected-transform", "unsupported-subresource")


def mutate(archive, mode):
    files = unpack(archive)
    if mode in ("stop-texture", "remove-texture", "replace-texture"):
        database = json.loads(files["assets_db/database.db"])
        manifest = json.loads(files["config/assets.json"])
        for entry in database["content"]:
            if entry["uid"].endswith("666666666690"):
                old = "assets_db/" + entry["dbPath"]
                entry["dbPath"] = entry["dbPath"].removesuffix(".ntex") + ".probe-delayed-ntex"
                current = "assets_db/" + entry["dbPath"]
                files[current] = files.pop(old)
                manifest["requiredFiles"] = [current if path == old else path for path in manifest["requiredFiles"]]
        files["assets_db/database.db"] = json.dumps(database).encode()
        files["config/assets.json"] = json.dumps(manifest).encode()
    elif mode in ("missing-texture", "corrupt-texture", "texture-dimensions"):
        path = next(path for path in files if path.endswith("666666666690.ntex"))
        if mode == "missing-texture": del files[path]
        elif mode == "corrupt-texture": files[path] = files[path][:28]
        else:
            data = bytearray(files[path]); data[8:12] = b"\xff\xff\xff\xff"; files[path] = bytes(data)
    elif mode in ("stop-load", "remove-load"):
        database = json.loads(files["assets_db/database.db"])
        manifest = json.loads(files["config/assets.json"])
        for entry in database["content"]:
            if entry["dbPath"].endswith(".gltf"):
                previous = "assets_db/" + entry["dbPath"]
                entry["dbPath"] = entry["dbPath"].removesuffix(".gltf") + ".probe-delayed-gltf"
                current = "assets_db/" + entry["dbPath"]
                files[current] = files.pop(previous)
                manifest["requiredFiles"] = [current if path == previous else path for path in manifest["requiredFiles"]]
        files["assets_db/database.db"] = json.dumps(database).encode()
        files["config/assets.json"] = json.dumps(manifest).encode()
    elif mode == "missing-material":
        del files["materials/portable_blue.json"]
    elif mode == "corrupt-material":
        files["materials/portable_blue.json"] = b'{"version":2,"baseColor":[1,0,0]}'
    elif mode in ("missing-geometry", "corrupt-geometry", "unsupported-topology", "unsupported-skinning", "invalid-indices"):
        path = next(path for path in files if path.endswith("666666666672.gltf"))
        model = json.loads(files[path])
        binary = str(__import__("pathlib").PurePosixPath(path).parent / model["buffers"][0]["uri"])
        if mode == "missing-geometry":
            del files[binary]
        elif mode == "corrupt-geometry":
            files[binary] = files[binary][:4]
        elif mode == "unsupported-topology":
            model["meshes"][0]["primitives"][0]["mode"] = 1
            files[path] = json.dumps(model).encode()
        elif mode == "unsupported-skinning":
            model["skins"] = [{"joints": [0]}]
            files[path] = json.dumps(model).encode()
        else:
            accessor = model["accessors"][model["meshes"][0]["primitives"][0]["indices"]]
            view = model["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            data = bytearray(files[binary])
            data[offset:offset+2] = b'\xff\xff'
            files[binary] = bytes(data)
    else:
        path = next(path for path in files if path.endswith("666666666684.nscene"))
        header, objects = read_scene(files[path])
        for obj in objects:
            if mode == "no-camera":
                obj["additionalComponents"] = [component for component in obj["additionalComponents"] if component["componentTypeName"] != "nau::scene::CameraComponent"]
                obj["additionalComponentCount"] = 1 + len(obj["additionalComponents"])
            for component in [obj["rootComponent"]] + obj["additionalComponents"]:
                if mode == "invalid-billboard-size" and component["componentTypeName"] == "nau::scene::BillboardComponent":
                    component["properties"]["screenPercentageSize"] = -1
                if mode == "invalid-camera" and component["componentTypeName"] == "nau::scene::CameraComponent":
                    component["properties"]["FieldOfView"] = 0
                if obj["name"] == "BlueCube" and component is obj["rootComponent"]:
                    if mode in ("singular-transform", "reflected-transform"):
                        for transform in (component["transform"], component["properties"]["transform"]):
                            transform["scale"][0] = 0 if mode == "singular-transform" else -1
                    if mode == "unsupported-subresource":
                        component["properties"]["geometry"] = component["properties"]["geometry"].replace("mesh/0", "mesh/1")
        files[path] = write_scene(header, objects)
    return pack(files)
