#include "std_testcase.h"
#include <wchar.h>
void case_sink(char * data)
{
    {
        size_t i;
        char source[100];
        memset(source, 'C', 100-1);
        source[100-1] = '\0';
        for (i = 0; i < 100; i++)
        {
            data[i] = source[i];
        }
        data[100-1] = '\0';
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
