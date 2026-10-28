#include "std_testcase.h"
#include <wchar.h>
void case_sink(char * data)
{
    {
        char source[100];
        memset(source, 'C', 100-1);
        source[100-1] = '\0';
        strncat(data, source, 100);
        printLine(data);
    }
}
void case_entry()
{
    char * data;
    char * buffer_9 = (char *)ALLOCA(50*sizeof(char));
    char * buffer_10 = (char *)ALLOCA(100*sizeof(char));
    data = buffer_9;
    data[0] = '\0';
    case_sink(data);
}
