package io.github.cheeringsoul.analyzer;

import io.github.cheeringsoul.analyzer.pojo.DataView;
import io.github.cheeringsoul.persistence.pojo.Base;

public interface AggregatedAnalyzer<E extends DataView, T extends Base> {
    E aggregate(T data);
}
