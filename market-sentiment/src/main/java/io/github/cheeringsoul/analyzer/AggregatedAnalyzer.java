package io.github.cheeringsoul.analyzer;

import io.github.cheeringsoul.pojo.Base;

public interface AggregatedAnalyzer<T extends Base> {
    AnalysisResult aggregate(T data);
}
