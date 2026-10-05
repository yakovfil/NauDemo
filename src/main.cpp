#include "demo_application.h"
#include "demo_platform.h"
#include "nau/app/run_application.h"

int main()
{
    const int code = nau::runApplication(nau::demo::createDemoApplication(),
                                         {.scheduling = nau::ApplicationScheduling::Presentation});
    return nau::demo::demoFailed() ? 1 : code;
}
