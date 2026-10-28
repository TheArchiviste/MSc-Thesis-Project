#include "std_testcase.h"
#ifndef _WIN32
#include <wchar.h>
#endif
#define SRC_STRING "AAAAAAAAAA"
void case_sink(char * data)
{
    {
        char source[10+1] = SRC_STRING;
        strcpy(data, source);
        printLine(data);
    }
}
void case_entry()
{
    char * data;
    char * buffer_7 = (char *)ALLOCA((10)*sizeof(char));
    char * buffer_8 = (char *)ALLOCA((10+1)*sizeof(char));
    data = buffer_8;
    data[0] = '\0';
    case_sink(data);
}
