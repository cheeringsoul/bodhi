package io.github.cheeringsoul.pojo;

import lombok.Builder;
import lombok.Getter;
import lombok.experimental.Accessors;

@Builder
@Getter
@Accessors(fluent = true)
public class Impression {
    long chatId;
    long relatedId;
    SourceType sourceType;
    String groupName;
    int views;
    String internal;
}
