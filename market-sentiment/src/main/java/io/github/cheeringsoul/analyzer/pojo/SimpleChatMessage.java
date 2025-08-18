package io.github.cheeringsoul.analyzer.pojo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.Setter;
import lombok.experimental.Accessors;

@Getter
@Setter
@Accessors(fluent = true)
@AllArgsConstructor
public class SimpleChatMessage {
    Long sender;
    String text;
}
