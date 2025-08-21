package io.github.cheeringsoul.persistence.pojo;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class MarketSentimentCount {
    private String symbol;
    private String sentiment;
    private int count;
}
