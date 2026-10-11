// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include "click_feedback.h"
#ifdef NAU_DEMO_PORTABLE_AUDIO
    #include "nau/app/application.h"
    #include "nau/input.h"
    #include "nau/service/service_provider.h"
    #include "nau_project_policy.h"

nau::async::Task<> DemoClickFeedback::preparePackagedScene()
{
    if (std::string_view(nau::project::StartupConfiguration) == "/config/battlezone_scene.json")
        return nau::async::Task<>::makeResolved();
    auto clip = nau::getServiceProvider().get<nau::audio::IPortableAudio>().loadClip(nau::project::ClickSound);
    if (!clip)
        return nau::async::Task<>::makeRejected(clip.getError());
    m_clip = *clip;
    m_reset = nau::input::inputResetGeneration();
    return nau::async::Task<>::makeResolved();
}

void DemoClickFeedback::gamePreUpdate(std::chrono::milliseconds)
{
    using namespace nau;
    using namespace nau::input;
    auto& audio = getServiceProvider().get<audio::IPortableAudio>();
    if (getApplication().isClosing() || !m_clip)
        return;
    if (audio.outputState() == audio::OutputState::Failed)
    {
        NAU_LOG_ERROR("Portable audio device failed");
        getApplication().stop();
        return;
    }
    const auto reset = inputResetGeneration();
    if (reset != m_reset)
    {
        audio.cancelPending();
        m_reset = reset;
    }
    if (reset != inputFrameResetGeneration())
        return;
    unsigned presses = 0;
    for (auto key : {Key::W, Key::A, Key::S, Key::D, Key::Q, Key::E})
        presses += keyboardPressCount(0, key);
    for (auto button : {MouseKey::ButtonLeft, MouseKey::ButtonMiddle, MouseKey::ButtonRight})
        presses += mousePressCount(0, button);
    if (reset != inputResetGeneration())
    {
        audio.cancelPending();
        return;
    }
    for (unsigned i = 0; i < presses; ++i)
    {
        auto result = audio.play(m_clip);
        if (!result)
        {
            NAU_LOG_ERROR("Click playback failed: {}", result.getError()->getDiagMessage());
            getApplication().stop();
            break;
        }
    }
}

void DemoClickFeedback::packagedSceneReady()
{
    nau::input::discardPendingPresses();
    nau::getServiceProvider().get<nau::audio::IPortableAudio>().cancelPending();
    m_reset = nau::input::inputResetGeneration();
}
#endif
