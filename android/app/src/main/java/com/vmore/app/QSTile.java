package com.vmore.app;

import android.graphics.drawable.Icon;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/**
 * The Quick Settings tile: pause or resume the queue from the phone's own
 * settings panel, without opening the app.
 */
public class QSTile extends TileService {

    @Override
    public void onStartListening() {
        super.onStartListening();
        paint();
    }

    @Override
    public void onClick() {
        super.onClick();
        if (Jobs.get(this).pausedAll()) {
            QueueService.resumeAll(this);
        } else {
            QueueService.pauseAll(this);
        }
        paint();
    }

    private void paint() {
        Tile tile = getQsTile();
        if (tile == null) {
            return;
        }
        boolean paused = Jobs.get(this).pausedAll();
        boolean running = QueueService.running() && !paused;
        tile.setState(running ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        tile.setLabel(getString(R.string.app_name));
        tile.setIcon(Icon.createWithResource(this,
                running ? R.drawable.ic_pause : R.drawable.ic_play));
        tile.updateTile();
    }
}
