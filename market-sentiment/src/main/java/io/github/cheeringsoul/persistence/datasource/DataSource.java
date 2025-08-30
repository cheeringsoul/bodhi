package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.pojo.Base;

public interface DataSource<T extends Base> {
    default T read() {
        return null;
    }

    default void save(T t) {
    }

    void close();
}
