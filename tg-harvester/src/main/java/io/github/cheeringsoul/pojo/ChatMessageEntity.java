package io.github.cheeringsoul.pojo;

import lombok.Getter;
import lombok.experimental.Accessors;

import java.time.Instant;
import java.util.List;

@Getter
@Accessors(fluent = true)
public class ChatMessageEntity extends BaseEntity {
    public ChatMessageEntity(long messageId, long chatId, long senderId, String groupName, String messageText, List<String> urls, Instant timestamp) {
        super(messageId, senderId, chatId, groupName, messageText, urls, timestamp);
    }
}
