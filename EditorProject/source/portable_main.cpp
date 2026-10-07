// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.

#include "nau/app/run_application.h"
#include "nau/scene/packaged_scene_application.h"
#include "nau_project_policy.h"

int main(int argc, char** argv)
{
    nau::scene::PackagedSceneOptions options;
    options.configurationPath = argc > 1 ? argv[1] : nau::project::StartupConfiguration;
    if (argc > 2)
    {
        options.archivePath = argv[2];
    }
    options.supportedComponents = nau::project::SupportedComponents;
    return nau::runApplication(nau::scene::createPackagedSceneApplication(std::move(options)));
}
