package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.pojo.Base;

public interface DataSource<T extends Base, E> {
    default T read() {
        return null;
    }

    default E save(T t) {
        return null;
    }

    default void close() {
    }
}
