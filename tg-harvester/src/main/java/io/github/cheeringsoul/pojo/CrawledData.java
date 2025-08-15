package io.github.cheeringsoul.pojo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.experimental.Accessors;
import org.jsoup.nodes.Document;

@Getter
@AllArgsConstructor
@Accessors(fluent = true)
public class CrawledData {
    private String url;
    private String title;
    private String content;
    private Document doc;
}