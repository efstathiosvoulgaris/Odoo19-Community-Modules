/** @odoo-module **/

import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import { patch } from '@web/core/utils/patch';
import { AlertDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from "@web/core/l10n/translation";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { loadImage } from "@point_of_sale/utils";

const MAX_IMAGE_SIZE = 5 * 1024 * 1024;

patch(FloorScreen.prototype, {
    async uploadTableImage(table) {
        if (!table) return;

        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';

        input.addEventListener('change', async (event) => {
            const file = event.target.files[0];
            if (!file) return;

            if (file.size > MAX_IMAGE_SIZE) {
                this.dialog.add(AlertDialog, {
                    title: _t("File Too Large"),
                    body: _t("Please select an image smaller than 5MB."),
                });
                return;
            }

            try {
                this.env.services.ui.block();
                const imageUrl = await getDataURLFromFile(file);
                const loadedImage = await loadImage(imageUrl);

                if (loadedImage) {
                    await this.pos.data.ormWrite("restaurant.table", [table.id], {
                        background_image: imageUrl.split(",")[1],
                    });
                    await this.pos.data.read("restaurant.table", [table.id]);
                } else {
                    this.dialog.add(AlertDialog, {
                        title: _t("Loading Image Error"),
                        body: _t("Failed to load the image. Please ensure the image is not corrupted and try again."),
                    });
                }
            } catch (error) {
                console.error('Table image upload error:', error);
                this.dialog.add(AlertDialog, {
                    title: _t("Image Upload Error"),
                    body: _t("An error occurred while processing the image. Please try again."),
                });
            } finally {
                this.env.services.ui.unblock();
            }
        }, { once: true });

        input.click();
    }
});
