from core import models, enums


def auto_create_views(image: models.Image):
    # Lets outcreated some views
    if image.rgb_views.count() == 0:
        # Create New Context
        

        # Create New View
        if image.store.c_size == 3:
            rgb_context = models.RGBRenderContext.objects.create(governed_by=image, name="RGB", description="Default RGB Context")

            red_view = models.RGBView.objects.create(image=image, context=rgb_context, color_map=enums.ColorMapChoices.RED)
            green_view = models.RGBView.objects.create(image=image, context=rgb_context, color_map=enums.ColorMapChoices.GREEN)
            blue_view = models.RGBView.objects.create(image=image, context=rgb_context, color_map=enums.ColorMapChoices.BLUE)


        else:
            for i in range(image.store.c_size):
                rgb_context = models.RGBRenderContext.objects.create(governed_by=image, name=f"Channel {i}", description=f"Default Render for Channel {i}")
                models.RGBView.objects.create(image=image, context=rgb_context, color_map=enums.ColorMapChoices.VIRIDIS)

    else:
        print("Views already created")