package com.example;

/**
 * Regression fixture for the "phantom method" bug.
 *
 * This class has a class-level @bodhi.implements, which triggers tag
 * inheritance for every matched method. If the Java function-pattern
 * regex is too loose, lines like `new JsonArray(...)` inside method
 * bodies get captured as phantom methods named "JsonArray", producing
 * false method-overloading warnings.
 *
 * @bodhi.implements PhantomService
 */
public class PhantomMethod {

    public void doStuff() {
        // These must NOT be parsed as method declarations.
        Object a = new JsonArray();
        Object b = new JsonArray();
        Object c = new JsonArray();
        foo.bar(new Helper());
        return new Wrapper(x);
    }
}
