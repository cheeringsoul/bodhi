package io.github.cheeringsoul.pojo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.experimental.Accessors;

import java.util.List;


@Getter
@AllArgsConstructor
@Accessors(fluent = true)
public class TextMessage {
    private String text;
    private List<String> urls;
}
