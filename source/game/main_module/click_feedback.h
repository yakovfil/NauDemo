// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#pragma once
#ifdef NAU_DEMO_PORTABLE_AUDIO
    #include "nau/app/main_loop/game_system.h"
    #include "nau/audio/portable_audio.h"
    #include "nau/rtti/rtti_impl.h"
    #include "nau/scene/packaged_scene_application.h"

class DemoClickFeedback final : public nau::scene::IPackagedScenePreparation,
                                public nau::IGamePreUpdate,
                                public nau::IRttiObject
{
    NAU_RTTI_CLASS(DemoClickFeedback, nau::scene::IPackagedScenePreparation, nau::IGamePreUpdate, nau::IRttiObject)
    nau::audio::Clip m_clip;
    unsigned m_reset = 0;
    nau::async::Task<> preparePackagedScene() override;
    void packagedSceneReady() override;
    void gamePreUpdate(std::chrono::milliseconds) override;
};
#endif
