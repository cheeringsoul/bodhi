package io.github.cheeringsoul.analyzer.pojo;

import java.time.Instant;
import java.util.Map;

public interface MarketActivity extends DataView {
    int messageCount();

    Instant startTime();

    Instant endTime();

    Map<String, Integer> relatedSymbols();
}
