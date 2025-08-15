package io.github.cheeringsoul.pojo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.experimental.Accessors;

import java.time.Instant;
import java.util.List;

@Getter
@AllArgsConstructor
@Accessors(fluent = true)
public class BaseEntity {
    protected long messageId;
    protected long senderId;
    protected long chatId;
    protected String groupName;
    protected String messageText;
    protected List<String> urls;
    protected Instant timestamp;
}
