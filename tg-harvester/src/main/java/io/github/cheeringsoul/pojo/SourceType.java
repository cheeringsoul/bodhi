package io.github.cheeringsoul.pojo;

public enum SourceType {
    CHAT(0),
    CHANNEL_NEWS(1);

    private final int value;

    private SourceType(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }
}