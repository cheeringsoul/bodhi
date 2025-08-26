package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.pojo.Base;

public interface DataSource<T extends Base> {
    T read();

    void close();
}
