#include "std_testcase.h"
#include <wchar.h>
void case_sink(char * data)
{
    {
        char dest[50] = "";
        strcpy(dest, data);
        printLine(data);
    }
}
void case_entry()
{
    char * data;
    char * dataBuffer = (char *)ALLOCA(100*sizeof(char));
    data = dataBuffer;
    memset(data, 'A', 100-1);
    data[100-1] = '\0';
    case_sink(data);
}
