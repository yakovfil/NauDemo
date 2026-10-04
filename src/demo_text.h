#pragma once

#include <cstdlib>

#include "nau/service/service_provider.h"
#include "nau/text/screen_text.h"

namespace nau::demo
{
    inline float textSetting(const char* name, float fallback)
    {
        const char* value = std::getenv(name);
        return value ? std::strtof(value, nullptr) : fallback;
    }
    inline Result<text::TextHandle> createDemoText(std::string_view path = "/demo/fonts/Abel-Regular.ttf")
    {
        auto& service = getServiceProvider().get<text::ScreenText>();
        if (const char* asset = std::getenv("NAU_DEMO_TEXT_FONT"))
            path = asset;
        auto font = service.loadFont(getServiceProvider().get<io::IVirtualFileSystem>(), path);
        if (!font)
            return font.getError();
        const char* label = std::getenv("NAU_DEMO_TEXT");
        return service.createText(*font, label ? label : "Nau Demo", textSetting("NAU_DEMO_TEXT_SIZE", 24));
    }

    inline Result<> drawDemoText(text::TextHandle label)
    {
        return getServiceProvider().get<text::ScreenText>().draw(std::move(label),
                                                                 {textSetting("NAU_DEMO_TEXT_X", 24), textSetting("NAU_DEMO_TEXT_Y", 24)},
                                                                 {textSetting("NAU_DEMO_TEXT_R", 1), textSetting("NAU_DEMO_TEXT_G", 1),
                                                                  textSetting("NAU_DEMO_TEXT_B", 1), textSetting("NAU_DEMO_TEXT_A", 1)});
    }
}  // namespace nau::demo
