package io.github.cheeringsoul.pojo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.Setter;
import lombok.experimental.Accessors;

import java.time.Instant;

@Getter
@Setter
@AllArgsConstructor
@Accessors(fluent = true)
public class LinkContent {
    private String url;
    private String title;
    private String content;
    CrawledData crawledData;
    private Instant timestamp;
}
