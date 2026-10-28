#include "std_testcase.h"
#include <wchar.h>
#ifdef _WIN32
#define SNPRINTF _snprintf
#else
#define SNPRINTF snprintf
#endif
void case_sink(char * data)
{
    {
        char source[100];
        memset(source, 'C', 100-1);
        source[100-1] = '\0';
        SNPRINTF(data, 100, "%s", source);
        printLine(data);
    }
}
void case_entry()
{
    char * data;
    char * buffer_9 = (char *)ALLOCA(50*sizeof(char));
    char * buffer_10 = (char *)ALLOCA(100*sizeof(char));
    data = buffer_10;
    data[0] = '\0';
    case_sink(data);
}
