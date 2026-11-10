package com.vmore.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/**
 * The queue: what is running, what is waiting and what needs another try —
 * with the controls for all of it (pause everything, resume, clear, per-job
 * pause, retry and remove).
 */
public class QueueActivity extends Activity implements Jobs.Listener {

    private LinearLayout jobList;
    private TextView empty;
    private TextView summary;
    private Button pauseAll;
    private Button resumeAll;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable watcher = new Runnable() {
        @Override
        public void run() {
            render();
            handler.postDelayed(this, 700);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Skin.prepare(this);
        setContentView(R.layout.activity_queue);
        jobList = findViewById(R.id.jobList);
        empty = findViewById(R.id.queueEmpty);
        summary = findViewById(R.id.queueSummary);
        pauseAll = findViewById(R.id.pauseAllButton);
        resumeAll = findViewById(R.id.resumeAllButton);

        findViewById(R.id.backButton).setOnClickListener(v -> finish());
        findViewById(R.id.clearButton).setOnClickListener(v -> {
            Jobs.get(this).removeFinished();
            render();
        });
        findViewById(R.id.retryAllButton).setOnClickListener(v -> {
            int woken = Jobs.get(this).retryFailed();
            if (woken == 0) {
                Ui.toast(this, getString(R.string.queue_nothing_failed));
            } else {
                QueueService.run(this);
                Ui.toast(this, woken + " " + getString(R.string.queue_retried));
            }
            render();
        });
        findViewById(R.id.stopAllButton).setOnClickListener(v ->
                Ui.confirm(this, getString(R.string.queue_stop_all),
                        getString(R.string.queue_stop_confirm),
                        getString(R.string.queue_stop_all), () -> {
                            QueueService.stopJob(this, null);
                            render();
                        }));
        pauseAll.setOnClickListener(v -> {
            QueueService.pauseAll(this);
            render();
        });
        resumeAll.setOnClickListener(v -> {
            QueueService.resumeAll(this);
            render();
        });
        for (View view : new View[]{pauseAll, resumeAll, findViewById(R.id.clearButton),
                findViewById(R.id.retryAllButton), findViewById(R.id.stopAllButton)}) {
            Anim.pressible(view);
        }
        Anim.pageIn(findViewById(R.id.queueHeader));
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (Lock.guard(this)) {
            return;
        }
        Jobs.get(this).addListener(this);
        handler.post(watcher);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(watcher);
        Jobs.get(this).removeListener(this);
        super.onPause();
    }

    @Override
    public void onJobsChanged() {
        render();
    }

    private void render() {
        List<QJob> jobs = Jobs.get(this).all();
        List<QJob> ordered = new ArrayList<>(jobs.size());
        for (QJob job : jobs) {
            if (job.isActive()) {
                ordered.add(job);
            }
        }
        for (QJob job : jobs) {
            if (QJob.QUEUED.equals(job.stage)) {
                ordered.add(job);
            }
        }
        for (QJob job : jobs) {
            if (QJob.PAUSED.equals(job.stage) || QJob.FAILED.equals(job.stage)) {
                ordered.add(job);
            }
        }

        boolean paused = Jobs.get(this).pausedAll();
        pauseAll.setEnabled(!paused);
        resumeAll.setEnabled(paused);
        int queued = Jobs.get(this).countInStage(QJob.QUEUED);
        int failed = Jobs.get(this).countInStage(QJob.FAILED);
        summary.setText(ordered.size() + " jobs • " + queued + " waiting"
                + (failed > 0 ? " • " + failed + " failed" : "")
                + (paused ? " • paused" : ""));

        if (ordered.isEmpty()) {
            jobList.removeAllViews();
            empty.setVisibility(View.VISIBLE);
            return;
        }
        empty.setVisibility(View.GONE);

        //: Rebuild rows only when the shape changed; otherwise just refresh the
        //: numbers, so a running progress bar never flickers.
        if (jobList.getChildCount() != ordered.size()
                || !sameOrder(ordered)) {
            jobList.removeAllViews();
            int index = 0;
            for (QJob job : ordered) {
                View row = LayoutInflater.from(this).inflate(R.layout.item_job, jobList, false);
                bind(row, job);
                jobList.addView(row);
                Anim.itemIn(row, index++);
            }
            return;
        }
        for (int index = 0; index < ordered.size(); index++) {
            bind(jobList.getChildAt(index), ordered.get(index));
        }
    }

    private List<String> lastOrder = new ArrayList<>();

    private boolean sameOrder(List<QJob> jobs) {
        List<String> now = new ArrayList<>();
        for (QJob job : jobs) {
            now.add(job.id);
        }
        boolean same = now.equals(lastOrder);
        lastOrder = now;
        return same;
    }

    private void bind(View row, QJob job) {
        ImageView icon = row.findViewById(R.id.jobIcon);
        TextView title = row.findViewById(R.id.jobTitle);
        TextView stage = row.findViewById(R.id.jobStage);
        ProgressBar bar = row.findViewById(R.id.jobProgress);
        TextView percent = row.findViewById(R.id.jobPercent);
        Button action = row.findViewById(R.id.jobAction);
        Button open = row.findViewById(R.id.jobOpen);
        Button remove = row.findViewById(R.id.jobRemove);

        icon.setImageResource(Ui.iconForKind(job.kind));
        title.setText(job.title());
        StringBuilder info = new StringBuilder(Ui.stageLabel(job.stage));
        if (job.size > 0) {
            info.append(" • ").append(Format.size(job.size));
        }
        if (!job.destTitle.isEmpty()) {
            info.append(" • ").append(job.destTitle);
        }
        if (QJob.FAILED.equals(job.stage) && !job.error.isEmpty()) {
            info.append(" • ").append(job.error);
        }
        stage.setText(info.toString());

        int value = job.percent();
        boolean active = job.isActive();
        bar.setVisibility(active || value > 0 ? View.VISIBLE : View.GONE);
        bar.setIndeterminate(active && job.size <= 0);
        bar.setProgress(value);
        percent.setText(active ? value + "%" : "");
        percent.setVisibility(active ? View.VISIBLE : View.GONE);

        if (QJob.PAUSED.equals(job.stage)) {
            action.setText(R.string.queue_resume);
            action.setOnClickListener(v -> {
                job.stage = QJob.QUEUED;
                Jobs.get(this).update(job);
                QueueService.run(this);
            });
        } else if (QJob.FAILED.equals(job.stage)) {
            action.setText(R.string.queue_retry);
            action.setOnClickListener(v -> {
                job.error = "";
                job.attempts = 0;
                //: Same reason as Retry all: a fresh link reference beats the
                //: one Telegram already turned down.
                job.fileId = 0;
                job.stage = QJob.QUEUED;
                Jobs.get(this).update(job);
                QueueService.run(this);
            });
        } else {
            action.setText(R.string.queue_pause);
            action.setOnClickListener(v -> {
                if (job.isActive()) {
                    QueueService.stopJob(this, job.id);
                } else {
                    job.stage = QJob.PAUSED;
                    Jobs.get(this).update(job);
                }
            });
        }

        boolean local = LocalFiles.exists(job.path);
        open.setVisibility(local ? View.VISIBLE : View.GONE);
        if (local) {
            open.setOnClickListener(v -> {
                Intent intent = new Intent(this, ViewerActivity.class);
                intent.putExtra("path", job.path);
                startActivity(intent);
            });
        }
        remove.setOnClickListener(v -> {
            QueueService.removeJob(this, job.id);
            render();
        });

        //: Waiting jobs can be pulled up or pushed down: the engine always takes
        //: the first one in the list.
        View up = row.findViewById(R.id.jobUp);
        View down = row.findViewById(R.id.jobDown);
        boolean waiting = QJob.QUEUED.equals(job.stage);
        up.setVisibility(waiting ? View.VISIBLE : View.INVISIBLE);
        down.setVisibility(waiting ? View.VISIBLE : View.INVISIBLE);
        up.setOnClickListener(v -> Jobs.get(this).move(job.id, -1));
        down.setOnClickListener(v -> Jobs.get(this).move(job.id, 1));
        Anim.pressible(up);
        Anim.pressible(down);
        Anim.pressible(action);
        Anim.pressible(open);
        Anim.pressible(remove);
    }
}
