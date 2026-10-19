package org.apache.commons.csv;
import java.io.StringReader;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class CarriageReturnTest {
 @Test public void countsCarriageReturnSeparators() throws Exception {
   ExtendedBufferedReader reader = new ExtendedBufferedReader(new StringReader("a\rb\rc"));
   while (reader.read() != -1) { }
   assertEquals(2, reader.getLineNumber());
 }
}
