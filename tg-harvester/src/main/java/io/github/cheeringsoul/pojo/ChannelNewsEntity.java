package io.github.cheeringsoul.pojo;

import lombok.Getter;
import lombok.experimental.Accessors;

import java.time.Instant;
import java.util.List;

@Getter
@Accessors(fluent = true)
public class ChannelNewsEntity extends BaseEntity {
    private final List<LinkContent> linkContents;

    public ChannelNewsEntity(long messageId, long chatId, String groupName, String messageText, List<String> urls, List<LinkContent> linkContents, Instant timestamp) {
        super(messageId, -1, chatId, groupName, messageText, urls, timestamp);
        this.linkContents = linkContents;
    }
}
