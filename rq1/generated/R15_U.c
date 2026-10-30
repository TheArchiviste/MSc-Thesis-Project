#include "std_testcase.h"
#include <wchar.h>
void case_sink(char * data)
{
    {
        char source[100];
        memset(source, 'C', 100-1);
        source[100-1] = '\0';
        strcpy(data, source);
        printLine(data);
        free(data);
    }
}
void case_entry()
{
    char * data;
    data = NULL;
    data = (char *)malloc(50*sizeof(char));
    if (data == NULL) {exit(-1);}
    data[0] = '\0';
    case_sink(data);
}
