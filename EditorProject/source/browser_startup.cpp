// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.

#include "nau/app/run_application.h"
#include "nau/scene/packaged_scene_application.h"

int main(int argc, char** argv)
{
    nau::scene::PackagedSceneOptions options;
    options.archivePath = "/project-package/content.nau_pack";
    if (argc == 2)
        options.configurationPath = argv[1];
    options.supportedComponents = {
        "nau::scene::SceneComponent", "nau::scene::CameraComponent",
        "nau::scene::StaticMeshComponent", "MyMover", "MyRotator"};
    return nau::runApplication(nau::scene::createPackagedSceneApplication(std::move(options)));
}
