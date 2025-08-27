package io.github.cheeringsoul;

import io.github.cheeringsoul.pojo.SourceType;
import lombok.Builder;
import lombok.Getter;
import lombok.experimental.Accessors;

import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

@Builder
@Getter
@Accessors(fluent = true)
class DelayedTask implements Delayed {
    private  long startTime; // 到期时间
    private  long chatId;
    private  long messageId;
    private String taskDelay;
    private SourceType sourceType;
    private String groupName;

    @Override
    public long getDelay(TimeUnit unit) {
        long diff = startTime - System.currentTimeMillis();
        return unit.convert(diff, TimeUnit.MILLISECONDS);
    }

    @Override
    public int compareTo(Delayed o) {
        return Long.compare(this.getDelay(TimeUnit.MILLISECONDS),
                o.getDelay(TimeUnit.MILLISECONDS));
    }

}
