package io.github.cheeringsoul.analyzer.pojo.internal;

import lombok.Data;
import lombok.experimental.Accessors;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Data
@Accessors(fluent = true)
public class MarketActivity implements io.github.cheeringsoul.analyzer.pojo.MarketActivity {
    private int messageCount;
    private final Map<String, Integer> relatedSymbols = new HashMap<>();
    private Instant startTime;
    private Instant endTime;

    public void incrementMessageCount() {
        messageCount++;
    }

    public void reset() {
        messageCount = 0;
        relatedSymbols.clear();
        startTime = null;
        endTime = null;
    }

}
